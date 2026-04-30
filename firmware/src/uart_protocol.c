#include "uart_protocol.h"
#include "ch32v20x_usart.h"
#include "ch32v20x_gpio.h"
#include "ch32v20x_rcc.h"
#include <string.h>
#include <stdio.h>

static char rx_buf[UART_RX_BUF_SIZE];
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

/* ---------- command dispatch (stub -- implemented in Plan 02) ---------- */

static void dispatch_command(const char *line) {
    /* Placeholder: echo back the line for testing serial I/O */
    usart2_send_string("ECHO ");
    usart2_send_string(line);
    usart2_send_string("\n");
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
}

void uart_protocol_tick(void) {
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
