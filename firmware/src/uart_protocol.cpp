/*
 * uart_protocol.c — 8N1 ASCII command/response protocol on USART2 (PA2/PA3)
 *
 * Decision: Motor RUN/STOP use Motion_control_set_PWM(ch, pwm) directly.
 * ams_state_set_loaded/unloaded are simple state-save helpers (persist to flash
 * which channel was "loaded" across resets). They do NOT start the motor.
 * Direct PWM is the correct path for Klipper-driven motor control.
 *
 * PWM range: 0-999 (timer period=999). 1% speed = 9.99 ≈ 10 PWM counts.
 * Positive PWM = forward, negative PWM = reverse, 0 = coast/stop.
 */

#include "uart_protocol.h"
#include "ch32v20x_usart.h"
#include "ch32v20x_gpio.h"
#include "ch32v20x_rcc.h"
#include "Motion_control.h"
#include "many_soft_AS5600.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

/* Upstream AS5600 instance defined in Motion_control.cpp */
extern AS5600_soft_IIC_many MC_AS5600;

/* ---------- feed distance calibration constant ---------- */

#ifndef GEAR_CIRCUMFERENCE_MM
#define GEAR_CIRCUMFERENCE_MM 30.0f  /* placeholder — measure on physical hardware */
#endif

/* ---------- module-level motor state ---------- */

static bool motor_running[4] = {false, false, false, false};
static int  motor_speed[4]   = {0, 0, 0, 0};
static int  motor_dir[4]     = {1, 1, 1, 1};  /* +1=FWD, -1=REV */

/* ---------- feed distance tracking state ---------- */

static int32_t  feed_counts[4]        = {0, 0, 0, 0};
static uint16_t prev_angle[4]         = {0, 0, 0, 0};
static bool     angle_initialized[4]  = {false, false, false, false};

/* ---------- AS5600 boot health state ---------- */

static int as5600_boot_status[4] = {0, 0, 0, 0};  /* cached at boot */

/* ---------- RX line buffer ---------- */

static char    rx_buf[UART_RX_BUF_SIZE];
static uint8_t rx_pos = 0;

/* ---------- low-level I/O ---------- */

static void usart2_send_char(char c) {
    while (!(USART2->STATR & USART_FLAG_TXE));
    USART2->DATAR = (uint8_t)c;
}

static void usart2_send_string(const char *s) {
    while (*s) {
        usart2_send_char(*s++);
    }
}

static int usart2_rx_available(void) {
    uint16_t sta = USART2->STATR;
    if (sta & USART_FLAG_ORE) {
        (void)USART2->DATAR;  /* clear ORE by reading DATAR */
    }
    return (sta & USART_FLAG_RXNE) ? 1 : 0;
}

static uint8_t usart2_rx_byte(void) {
    return (uint8_t)(USART2->DATAR & 0xFF);
}

/* ---------- feed distance functions ---------- */

static void update_feed_distance(int ch) {
    uint16_t now = MC_AS5600.raw_angle[ch];
    if (!angle_initialized[ch]) {
        prev_angle[ch] = now;
        angle_initialized[ch] = true;
        return;
    }
    int16_t delta = (int16_t)(now - prev_angle[ch]);
    feed_counts[ch] += delta;
    prev_angle[ch] = now;
}

static float get_feed_mm(int ch) {
    return (feed_counts[ch] / 4096.0f) * GEAR_CIRCUMFERENCE_MM;
}

/* ---------- AS5600 magnet status helpers ---------- */

static const char* mag_status_str(int stu) {
    switch (stu) {
        case 0:  return "ok";
        case 1:  return "low";
        case 2:  return "high";
        case -1: return "offline";
        default: return "unknown";
    }
}

static void send_boot_message(void) {
    char buf[80];
    for (int ch = 0; ch < 4; ch++) {
        as5600_boot_status[ch] = (int)MC_AS5600.magnet_stu[ch];
    }
    snprintf(buf, sizeof(buf), "BOOT mag0=%s mag1=%s mag2=%s mag3=%s\n",
        mag_status_str(as5600_boot_status[0]),
        mag_status_str(as5600_boot_status[1]),
        mag_status_str(as5600_boot_status[2]),
        mag_status_str(as5600_boot_status[3]));
    usart2_send_string(buf);
}

/* ---------- helpers ---------- */

/*
 * parse_channel: parse a single-digit channel number '0'-'3' from *s.
 * Returns 0-3 on success, -1 if *s is out of range.
 */
static int parse_channel(const char *s) {
    if (*s >= '0' && *s <= '3') return *s - '0';
    return -1;
}

/*
 * pct_to_pwm: convert 0-100 speed percentage to PWM counts (timer period=999).
 */
static int pct_to_pwm(int pct) {
    if (pct <= 0)   return 0;
    if (pct >= 100) return 999;
    return pct * 10;  /* 10 counts per percent; 100% = 1000 capped to 999 above */
}

/* ---------- STATUS response ---------- */

static void send_status_response(void) {
    char buf[256];
    int  pos = 0;

    pos += snprintf(buf + pos, (int)sizeof(buf) - pos, "STATUS ok");

    for (int ch = 0; ch < 4; ch++) {
        /* live magnet status (not cached boot status — may change while running) */
        const char *mag = mag_status_str((int)MC_AS5600.magnet_stu[ch]);

        /* direction string */
        const char *dir_s = (motor_dir[ch] >= 0) ? "FWD" : "REV";

        pos += snprintf(buf + pos, (int)sizeof(buf) - pos,
            " ch=%d fil=%d mot=%d spd=%d dir=%s mm=%.1f mag=%s",
            ch,
            filament_channel_inserted[ch] ? 1 : 0,
            motor_running[ch] ? 1 : 0,
            motor_speed[ch],
            dir_s,
            get_feed_mm(ch),
            mag
        );
    }

    pos += snprintf(buf + pos, (int)sizeof(buf) - pos, "\n");
    usart2_send_string(buf);
}

/* ---------- RUN command ---------- */

static void cmd_run(const char *args) {
    int ch = parse_channel(args);
    if (ch < 0) {
        usart2_send_string("ERR invalid channel\n");
        return;
    }

    int spd = (motor_speed[ch] > 0) ? motor_speed[ch] : 50;
    if (motor_speed[ch] == 0) motor_speed[ch] = 50;

    /* Apply signed PWM: positive=FWD, negative=REV */
    int pwm = pct_to_pwm(spd) * motor_dir[ch];
    Motion_control_set_PWM((uint8_t)ch, pwm);
    motor_running[ch] = true;

    char resp[32];
    snprintf(resp, sizeof(resp), "RUN ok ch=%d\n", ch);
    usart2_send_string(resp);
}

/* ---------- STOP command ---------- */

static void cmd_stop(const char *args) {
    int ch = parse_channel(args);
    if (ch < 0) {
        usart2_send_string("ERR invalid channel\n");
        return;
    }

    Motion_control_set_PWM((uint8_t)ch, 0);
    motor_running[ch] = false;

    char resp[32];
    snprintf(resp, sizeof(resp), "STOP ok ch=%d\n", ch);
    usart2_send_string(resp);
}

/* ---------- SPEED command ---------- */

static void cmd_speed(const char *args) {
    /* args: "<ch> <pct>" e.g. "0 75" */
    int ch = parse_channel(args);
    if (ch < 0) {
        usart2_send_string("ERR invalid channel\n");
        return;
    }

    /* skip past channel digit and expect a space */
    if (args[1] != ' ') {
        usart2_send_string("ERR invalid channel\n");
        return;
    }

    int pct = atoi(args + 2);
    if (pct < 0)   pct = 0;
    if (pct > 100) pct = 100;

    motor_speed[ch] = pct;

    /* Apply immediately if motor is running */
    if (motor_running[ch]) {
        int pwm = pct_to_pwm(pct) * motor_dir[ch];
        Motion_control_set_PWM((uint8_t)ch, pwm);
    }

    char resp[48];
    snprintf(resp, sizeof(resp), "SPEED ok ch=%d spd=%d\n", ch, pct);
    usart2_send_string(resp);
}

/* ---------- DIR command ---------- */

static void cmd_dir(const char *args) {
    /* args: "<ch> FWD" or "<ch> REV" */
    int ch = parse_channel(args);
    if (ch < 0) {
        usart2_send_string("ERR invalid channel\n");
        return;
    }

    if (args[1] != ' ') {
        usart2_send_string("ERR invalid channel\n");
        return;
    }

    const char *dir_str = args + 2;
    int new_dir;
    const char *dir_name;

    if (strncmp(dir_str, "FWD", 3) == 0) {
        new_dir  =  1;
        dir_name = "FWD";
    } else if (strncmp(dir_str, "REV", 3) == 0) {
        new_dir  = -1;
        dir_name = "REV";
    } else {
        usart2_send_string("ERR invalid direction\n");
        return;
    }

    motor_dir[ch] = new_dir;

    /* Re-apply PWM with new direction sign if motor is running */
    if (motor_running[ch]) {
        int pwm = pct_to_pwm(motor_speed[ch]) * motor_dir[ch];
        Motion_control_set_PWM((uint8_t)ch, pwm);
    }

    char resp[48];
    snprintf(resp, sizeof(resp), "DIR ok ch=%d dir=%s\n", ch, dir_name);
    usart2_send_string(resp);
}

/* ---------- command dispatch ---------- */

static void dispatch_command(const char *line) {
    if (strncmp(line, "STATUS", 6) == 0) {
        send_status_response();
    } else if (strncmp(line, "RUN ", 4) == 0) {
        cmd_run(line + 4);
    } else if (strncmp(line, "STOP ", 5) == 0) {
        cmd_stop(line + 5);
    } else if (strncmp(line, "SPEED ", 6) == 0) {
        cmd_speed(line + 6);
    } else if (strncmp(line, "DIR ", 4) == 0) {
        cmd_dir(line + 4);
    } else {
        usart2_send_string("ERR unknown command\n");
    }
}

/* ---------- public API ---------- */

void uart_protocol_init(void) {
    GPIO_InitTypeDef  g = {0};
    USART_InitTypeDef u = {0};

    RCC_APB1PeriphClockCmd(RCC_APB1Periph_USART2, ENABLE);
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA,  ENABLE);

    /* PA2 = USART2_TX (alt function push-pull) */
    g.GPIO_Pin   = GPIO_Pin_2;
    g.GPIO_Speed = GPIO_Speed_50MHz;
    g.GPIO_Mode  = GPIO_Mode_AF_PP;
    GPIO_Init(GPIOA, &g);

    /* PA3 = USART2_RX (input pull-up) */
    g.GPIO_Pin  = GPIO_Pin_3;
    g.GPIO_Mode = GPIO_Mode_IPU;
    GPIO_Init(GPIOA, &g);

    /* 8N1 at UART_BAUD (default 115200) */
    u.USART_BaudRate            = UART_BAUD;
    u.USART_WordLength          = USART_WordLength_8b;
    u.USART_StopBits            = USART_StopBits_1;
    u.USART_Parity              = USART_Parity_No;
    u.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
    u.USART_Mode                = USART_Mode_Tx | USART_Mode_Rx;
    USART_Init(USART2, &u);
    USART_Cmd(USART2, ENABLE);

    rx_pos = 0;

    /* Report AS5600 magnet health on boot */
    send_boot_message();
}

void uart_protocol_tick(void) {
    /* Update feed distance accumulators before processing RX */
    for (int ch = 0; ch < 4; ch++) {
        update_feed_distance(ch);
    }

    while (usart2_rx_available()) {
        char c = (char)usart2_rx_byte();

        if (c == '\n' || c == '\r') {
            if (rx_pos > 0) {
                rx_buf[rx_pos] = '\0';
                dispatch_command(rx_buf);
                rx_pos = 0;
            }
            continue;
        }

        if (rx_pos < UART_RX_BUF_SIZE - 1) {
            rx_buf[rx_pos++] = c;
        }
        /* else: overflow -- silently drop until newline */
    }
}
