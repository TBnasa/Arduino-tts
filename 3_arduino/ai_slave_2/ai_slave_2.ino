/*
 * AI Slave 2 TTS v9 — 3-Node 24kHz Dual-Core Extension
 * I2C Address: 9
 */

#include <Wire.h>
#include <avr/pgmspace.h>
#include "phonemes.h"

#define I2C_ADDR   9
#define MAX_TEXT   150
#define PLAY_HZ   24000

volatile uint8_t  tbuf[MAX_TEXT];
volatile uint8_t  tlen = 0, playing = 0, ph_idx = 0;
volatile uint16_t sp = 0;
volatile char     punc_mode = 'T'; // 'T' = statement, 'Q' = question, 'E' = exclamation
static   uint16_t cur_off, cur_len;
static   uint16_t nxt_off, nxt_len;
static   uint16_t prev_out = 0;

void prep_next() {
  if (ph_idx >= tlen) { cur_off = 0xFFFF; cur_len = 0; nxt_off = 0xFFFF; nxt_len = 0; return; }
  uint8_t ph = tbuf[ph_idx];
  if (ph >= PHONEME_COUNT) ph = PH_SPACE;
  
  cur_off = pgm_read_word(&ph_off[ph]);
  cur_len = pgm_read_word(&ph_len[ph]);

  if (ph_idx + 1 < tlen) {
    uint8_t nph = tbuf[ph_idx + 1];
    if (nph >= PHONEME_COUNT) nph = PH_SPACE;
    nxt_off = pgm_read_word(&ph_off[nph]);
    nxt_len = pgm_read_word(&ph_len[nph]);
  } else {
    nxt_off = 0xFFFF;
    nxt_len = 0;
  }
}

void setup() {
  Wire.begin(I2C_ADDR);
  Wire.setClock(100000); // 100kHz standard I2C Mode (highly stable over breadboard jumpers)
#if defined(ARDUINO_ARCH_AVR)
  Wire.setWireTimeout(3000, true); // Enable automatic I2C recovery on timeout
#endif
  Wire.onReceive(rx);

  pinMode(3, OUTPUT);
  pinMode(11, OUTPUT);
  
  TCCR2A = _BV(COM2A1) | _BV(COM2B1) | _BV(WGM21) | _BV(WGM20);
  TCCR2B = _BV(CS20);
  OCR2A = 128; OCR2B = 128;

  cli();
  TCCR1A = 0;
  TCCR1B = _BV(WGM12) | _BV(CS10);
  OCR1A = (16000000 / PLAY_HZ) - 1;
  TIMSK1 |= _BV(OCIE1A);
  sei();
}

void loop() { }

void rx(int n) {
  if (n < 1) return;
  char cmd = Wire.read();
  
  if (cmd == 'T' || cmd == 'Q' || cmd == 'E') {
    tlen = 0;
    punc_mode = cmd;
    playing = 0; // Don't start playing yet! Keep silent while receiving.
  } else if (cmd == 'S') {
    // SYNC PLAY trigger received! Start playback in perfect sync!
    ph_idx = 0; sp = 0;
    prev_out = 0;
    prep_next();
    playing = (tlen > 0);
    return;
  } else if (cmd != 'C') {
    return;
  }

  while (Wire.available() && tlen < MAX_TEXT) {
    tbuf[tlen++] = Wire.read();
  }
}

ISR(TIMER1_COMPA_vect) {
  static uint16_t slide_counter = 0;
  if (!playing || ph_idx >= tlen) {
    slide_counter = 0;
    DDRD |= (1 << 3); // ALWAYS OUTPUT mode! Restores 333 ohm parallel impedance for user's 100nF filter!
    OCR2A = 128; OCR2B = 128; playing = 0; return;
  }

  // Adjust playback pitch dynamically based on punctuation mode (Fast Math without division)
  if (punc_mode == 'E') {
    OCR1A = 600; // ~10% faster and higher pitch for exclamations!
  } else if (punc_mode == 'Q' && tlen >= 4 && ph_idx >= (tlen - 4)) {
    // Soru (?) pitch rise slide (smooth across last 200ms)
    uint16_t drop = slide_counter >> 6;
    if (drop > 100) drop = 100;
    OCR1A = 666 - drop; // Glide up
    slide_counter++;
  } else if (punc_mode == 'T' && tlen >= 4 && ph_idx >= (tlen - 4)) {
    // Statement drop slide (smooth across last 200ms)
    uint16_t rise = slide_counter >> 7;
    if (rise > 50) rise = 50;
    OCR1A = 666 + rise; // Glide down
    slide_counter++;
  } else {
    slide_counter = 0;
    OCR1A = 666; // Standard 24kHz pitch
  }

  uint8_t s = 128;
  if (cur_off != 0xFFFF) {
    s = pgm_read_byte(&pcm[cur_off + sp]);
  }

  // Crossfade (Smoothly fade between phonemes and fade out at sentence end to prevent pops)
  if (cur_len > CROSSFADE_SAMPLES && sp >= (cur_len - CROSSFADE_SAMPLES)) {
    uint16_t fade = sp - (cur_len - CROSSFADE_SAMPLES);
    uint16_t target_len = (nxt_len > 0) ? nxt_len : CROSSFADE_SAMPLES;
    if (fade < target_len) {
      uint8_t ns = 128;
      if (nxt_off != 0xFFFF && nxt_len > 0) {
        ns = pgm_read_byte(&pcm[nxt_off + fade]);
      }
      s = ((uint16_t)s * (CROSSFADE_SAMPLES - fade) + (uint16_t)ns * fade) / CROSSFADE_SAMPLES;
    }
  }

  // ALWAYS output the sample (active or crossfaded silence). 
  // This puts the three 1K resistors in parallel (333 Ohms), fixing the extreme lowpass muffling!
  DDRD |= (1 << 3); 
  OCR2A = s;
  OCR2B = s;

  sp++;
  if (sp >= cur_len) {
    ph_idx++; sp = 0;
    if (ph_idx >= tlen) { OCR2A=128; OCR2B=128; playing=0; }
    else prep_next();
  }
}
