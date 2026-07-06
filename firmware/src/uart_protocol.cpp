/*
 * uart_protocol.c — 8N1 ASCII command/response protocol on USART1 (PA9/PA10 → CH340 USB-C)
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
#include "ws2812.h"
#include "ch32v20x_usart.h"
#include "ch32v20x_gpio.h"
#include "ch32v20x_rcc.h"
#include "ch32v20x_iwdg.h"
#include "ch32v20x_tim.h"
#include "ch32v20x_misc.h"
#include "Motion_control.h"
#include "many_soft_AS5600.h"
#include "ADC_DMA.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

/* Upstream AS5600 instance defined in Motion_control.cpp */
extern AS5600_soft_IIC_many MC_AS5600;

/* LED instances defined in main.cpp */
extern WS2812_class SYS_RGB;
extern WS2812_class RGBOUT[4];

/* ---------- feed distance calibration constant ---------- */

#ifndef GEAR_CIRCUMFERENCE_MM
#define GEAR_CIRCUMFERENCE_MM 30.0f  /* placeholder — measure on physical hardware */
#endif

/* ---------- hardware enable state ---------- */

static bool hw_enabled = false;

/* ---------- LED status helpers ---------- */

static void led_set_enabled(int ch) {
    /* Red = enabled but stopped */
    RGBOUT[ch].set_RGB(255, 0, 0, 0);
    RGBOUT[ch].set_RGB(255, 0, 0, 1);
    RGBOUT[ch].updata();
}

static void led_set_running(int ch) {
    /* Green = motor running */
    RGBOUT[ch].set_RGB(0, 255, 0, 0);
    RGBOUT[ch].set_RGB(0, 255, 0, 1);
    RGBOUT[ch].updata();
}

static void led_set_off(int ch) {
    RGBOUT[ch].set_RGB(0, 0, 0, 0);
    RGBOUT[ch].set_RGB(0, 0, 0, 1);
    RGBOUT[ch].updata();
}

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

/* ---------- Interrupt-driven RX ring buffer ---------- */

#define IRQ_RX_BUF_SIZE 128
static volatile char    irq_rx_buf[IRQ_RX_BUF_SIZE];
static volatile uint8_t irq_rx_head = 0;  /* written by ISR */
static volatile uint8_t irq_rx_tail = 0;  /* read by main loop */

/* USART1 RX interrupt handler — buffers incoming bytes so they aren't
   lost during slow I2C operations in the main loop. */
extern "C" void USART1_IRQHandler(void) __attribute__((interrupt("WCH-Interrupt-fast")));
extern "C" void USART1_IRQHandler(void) {
    if (USART1->STATR & USART_FLAG_RXNE) {
        char c = (char)(USART1->DATAR & 0xFF);
        uint8_t next = (irq_rx_head + 1) % IRQ_RX_BUF_SIZE;
        if (next != irq_rx_tail) {  /* drop on overflow */
            irq_rx_buf[irq_rx_head] = c;
            irq_rx_head = next;
        }
    }
    if (USART1->STATR & USART_FLAG_ORE) {
        (void)USART1->DATAR;  /* clear overrun */
    }
}

/* ---------- RX line buffer ---------- */

static char    rx_buf[UART_RX_BUF_SIZE];
static uint8_t rx_pos = 0;

/* ---------- low-level I/O ---------- */

static void usart2_send_char(char c) {
    while (!(USART1->STATR & USART_FLAG_TXE));
    USART1->DATAR = (uint8_t)c;
}

static void usart2_send_string(const char *s) {
    while (*s) {
        usart2_send_char(*s++);
    }
}

static int usart2_rx_available(void) {
    return (irq_rx_head != irq_rx_tail) ? 1 : 0;
}

static uint8_t usart2_rx_byte(void) {
    uint8_t c = (uint8_t)irq_rx_buf[irq_rx_tail];
    irq_rx_tail = (irq_rx_tail + 1) % IRQ_RX_BUF_SIZE;
    return c;
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

/* Returns feed distance as integer tenths of mm (e.g. 1425 = 142.5mm) */
static int32_t get_feed_mm_x10(int ch) {
    return (int32_t)((feed_counts[ch] * (int32_t)(GEAR_CIRCUMFERENCE_MM * 10.0f)) / 4096);
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
    /* Sensors are updated by Motion_control_run() in the main loop */
    if (hw_enabled) {
        for (int ch = 0; ch < 4; ch++)
            update_feed_distance(ch);
    }

    char buf[256];
    int  pos = 0;

    pos += snprintf(buf + pos, (int)sizeof(buf) - pos, "STATUS ok");

    for (int ch = 0; ch < 4; ch++) {
        /* live magnet status (not cached boot status — may change while running) */
        const char *mag = mag_status_str((int)MC_AS5600.magnet_stu[ch]);

        /* direction string */
        const char *dir_s = (motor_dir[ch] >= 0) ? "FWD" : "REV";

        int32_t mm10 = get_feed_mm_x10(ch);
        int32_t mm_whole = mm10 / 10;
        int32_t mm_frac  = (mm10 < 0 ? -mm10 : mm10) % 10;

        pos += snprintf(buf + pos, (int)sizeof(buf) - pos,
            " ch=%d fil=%d mot=%d spd=%d dir=%s mm=%ld.%ld mag=%s",
            ch,
            filament_channel_inserted[ch] ? 1 : 0,
            motor_running[ch] ? 1 : 0,
            motor_speed[ch],
            dir_s,
            (long)mm_whole, (long)mm_frac,
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

/* ---------- LED command ---------- */

/*
 * LED <target> <R> <G> <B>
 *   target: "sys" for SYS_RGB, or "0"-"3" for channel RGBOUT
 *   R, G, B: 0-255
 *
 * LED off           — turn all LEDs off
 * LED sys 255 0 0   — system LED red
 * LED 0 0 255 0     — channel 0 LED green
 */
static void cmd_led(const char *args) {
    /* LED off — clear everything */
    if (strncmp(args, "off", 3) == 0) {
        SYS_RGB.set_RGB(0, 0, 0, 0);
        SYS_RGB.updata();
        for (int i = 0; i < 4; i++) {
            RGBOUT[i].set_RGB(0, 0, 0, 0);
            RGBOUT[i].set_RGB(0, 0, 0, 1);
            RGBOUT[i].updata();
        }
        usart2_send_string("LED ok all off\n");
        return;
    }

    /* parse target */
    int ch = -1;
    const char *rest = args;
    if (strncmp(args, "sys", 3) == 0) {
        ch = -1; /* sentinel for SYS_RGB */
        rest = args + 3;
    } else if (args[0] >= '0' && args[0] <= '3') {
        ch = args[0] - '0';
        rest = args + 1;
    } else {
        usart2_send_string("ERR invalid LED target\n");
        return;
    }

    if (*rest != ' ') {
        usart2_send_string("ERR expected R G B\n");
        return;
    }
    rest++;

    /* parse R G B */
    int r = atoi(rest);
    while (*rest && *rest != ' ') rest++;
    if (*rest == ' ') rest++;
    int g = atoi(rest);
    while (*rest && *rest != ' ') rest++;
    if (*rest == ' ') rest++;
    int b = atoi(rest);

    if (r < 0) r = 0; if (r > 255) r = 255;
    if (g < 0) g = 0; if (g > 255) g = 255;
    if (b < 0) b = 0; if (b > 255) b = 255;

    if (ch < 0) {
        /* SYS_RGB — single LED */
        SYS_RGB.set_RGB((uint8_t)r, (uint8_t)g, (uint8_t)b, 0);
        SYS_RGB.updata();
    } else {
        /* Channel RGBOUT — 2 LEDs per channel, set both */
        RGBOUT[ch].set_RGB((uint8_t)r, (uint8_t)g, (uint8_t)b, 0);
        RGBOUT[ch].set_RGB((uint8_t)r, (uint8_t)g, (uint8_t)b, 1);
        RGBOUT[ch].updata();
    }

    char resp[48];
    if (ch < 0)
        snprintf(resp, sizeof(resp), "LED ok sys r=%d g=%d b=%d\n", r, g, b);
    else
        snprintf(resp, sizeof(resp), "LED ok ch=%d r=%d g=%d b=%d\n", ch, r, g, b);
    usart2_send_string(resp);
}

/* ---------- ENABLE command ---------- */

static void cmd_enable(const char *args) {
    (void)args;
    if (hw_enabled) {
        usart2_send_string("ENABLE ok already\n");
        return;
    }

    /* Init ADC (filament switches) */
    ADC_DMA_init();
    ADC_DMA_wait_full();

    /* Init motors and AS5600 sensors */
    Motion_control_init();

    /* Snapshot AS5600 angles for feed distance tracking */
    for (int ch = 0; ch < 4; ch++) {
        prev_angle[ch] = MC_AS5600.raw_angle[ch];
        angle_initialized[ch] = true;
        feed_counts[ch] = 0;
    }

    hw_enabled = true;

    /* Set all channel LEDs to red (enabled but stopped) */
    for (int ch = 0; ch < 4; ch++)
        led_set_enabled(ch);

    /* Report sensor status */
    char buf[128];
    snprintf(buf, sizeof(buf),
        "ENABLE ok fil=%d%d%d%d mag=%s/%s/%s/%s\n",
        filament_channel_inserted[0] ? 1 : 0,
        filament_channel_inserted[1] ? 1 : 0,
        filament_channel_inserted[2] ? 1 : 0,
        filament_channel_inserted[3] ? 1 : 0,
        mag_status_str((int)MC_AS5600.magnet_stu[0]),
        mag_status_str((int)MC_AS5600.magnet_stu[1]),
        mag_status_str((int)MC_AS5600.magnet_stu[2]),
        mag_status_str((int)MC_AS5600.magnet_stu[3]));
    usart2_send_string(buf);
}

/* ---------- command dispatch ---------- */

static void dispatch_command(const char *line) {
    if (strncmp(line, "ENABLE", 6) == 0) {
        cmd_enable(line + 6);
    } else if (strncmp(line, "STATUS", 6) == 0) {
        send_status_response();
    } else if (strncmp(line, "RUN ", 4) == 0) {
        if (!hw_enabled) { usart2_send_string("ERR not enabled\n"); return; }
        cmd_run(line + 4);
    } else if (strncmp(line, "STOP ", 5) == 0) {
        if (!hw_enabled) { usart2_send_string("ERR not enabled\n"); return; }
        cmd_stop(line + 5);
    } else if (strncmp(line, "SPEED ", 6) == 0) {
        if (!hw_enabled) { usart2_send_string("ERR not enabled\n"); return; }
        cmd_speed(line + 6);
    } else if (strncmp(line, "DIR ", 4) == 0) {
        if (!hw_enabled) { usart2_send_string("ERR not enabled\n"); return; }
        cmd_dir(line + 4);
    } else if (strncmp(line, "LED ", 4) == 0) {
        cmd_led(line + 4);
    } else if (strncmp(line, "LED", 3) == 0 && line[3] == '\0') {
        usart2_send_string("ERR usage: LED <sys|0-3> <R> <G> <B> | LED off\n");
    } else {
        usart2_send_string("ERR unknown command\n");
    }
}

/* ---------- public API ---------- */

void uart_protocol_init(void) {
    GPIO_InitTypeDef  g = {0};
    USART_InitTypeDef u = {0};

    RCC_APB2PeriphClockCmd(RCC_APB2Periph_USART1 | RCC_APB2Periph_GPIOA, ENABLE);

    /* PA9 = USART1_TX (alt function push-pull) */
    g.GPIO_Pin   = GPIO_Pin_9;
    g.GPIO_Speed = GPIO_Speed_50MHz;
    g.GPIO_Mode  = GPIO_Mode_AF_PP;
    GPIO_Init(GPIOA, &g);

    /* PA10 = USART1_RX (input pull-up) */
    g.GPIO_Pin  = GPIO_Pin_10;
    g.GPIO_Mode = GPIO_Mode_IPU;
    GPIO_Init(GPIOA, &g);

    /* PA12 = RS-485 DE — keep HIGH (TX mode) for now */
    g.GPIO_Pin   = GPIO_Pin_12;
    g.GPIO_Speed = GPIO_Speed_50MHz;
    g.GPIO_Mode  = GPIO_Mode_Out_PP;
    GPIO_Init(GPIOA, &g);
    GPIOA->BSHR = GPIO_Pin_12;  /* DE HIGH = always transmit */

    /* 8N1 at UART_BAUD (default 115200) */
    u.USART_BaudRate            = UART_BAUD;
    u.USART_WordLength          = USART_WordLength_8b;
    u.USART_StopBits            = USART_StopBits_1;
    u.USART_Parity              = USART_Parity_No;
    u.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
    u.USART_Mode                = USART_Mode_Tx | USART_Mode_Rx;
    USART_Init(USART1, &u);

    /* Enable USART1 RX interrupt for non-blocking receive */
    USART_ITConfig(USART1, USART_IT_RXNE, ENABLE);
    NVIC_InitTypeDef nvic = {0};
    nvic.NVIC_IRQChannel = USART1_IRQn;
    nvic.NVIC_IRQChannelPreemptionPriority = 1;
    nvic.NVIC_IRQChannelSubPriority = 0;
    nvic.NVIC_IRQChannelCmd = ENABLE;
    NVIC_Init(&nvic);

    USART_Cmd(USART1, ENABLE);

    rx_pos = 0;
    irq_rx_head = 0;
    irq_rx_tail = 0;

    /* Init feed distance tracking from AS5600 (already init'd by Motion_control_init) */
    for (int ch = 0; ch < 4; ch++) {
        prev_angle[ch] = MC_AS5600.raw_angle[ch];
        angle_initialized[ch] = true;
        feed_counts[ch] = 0;
    }

    send_boot_message();
}

/* Check if a motor channel is actually being driven (PWM != brake/stop).
   When PWM=0 (stop), both compare registers are set to 1000 (brake).
   When driving, one side has PWM < 1000 and other has 0. */
static bool motor_is_active(int ch) {
    uint16_t c1, c2;
    switch (ch) {
    case 3: c1 = TIM2->CH1CVR; c2 = TIM2->CH2CVR; break;
    case 2: c1 = TIM3->CH1CVR; c2 = TIM3->CH2CVR; break;
    case 1: c1 = TIM4->CH1CVR; c2 = TIM4->CH2CVR; break;
    case 0: c1 = TIM4->CH3CVR; c2 = TIM4->CH4CVR; break;
    default: return false;
    }
    /* Brake = both 1000, coast = both 0. Active = one side has PWM */
    return !((c1 >= 1000 && c2 >= 1000) || (c1 == 0 && c2 == 0));
}

void uart_protocol_tick(void) {
    IWDG->CTLR = 0xAAAA; /* Feed watchdog */

    /* Update LEDs based on actual motor state */
    if (hw_enabled) {
        for (int ch = 0; ch < 4; ch++) {
            bool active = motor_is_active(ch);
            if (active && !motor_running[ch]) {
                motor_running[ch] = true;
                led_set_running(ch);
            } else if (!active && motor_running[ch]) {
                motor_running[ch] = false;
                led_set_enabled(ch);
            }
        }
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
