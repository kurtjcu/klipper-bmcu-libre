#ifndef UART_PROTOCOL_H
#define UART_PROTOCOL_H

#ifdef __cplusplus
extern "C" {
#endif

#ifndef UART_BAUD
#define UART_BAUD 115200
#endif

#define UART_RX_BUF_SIZE 64
#define UART_TX_BUF_SIZE 256

void uart_protocol_init(void);
void uart_protocol_tick(void);

#ifdef __cplusplus
}
#endif

#endif /* UART_PROTOCOL_H */
