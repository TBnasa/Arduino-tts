/*
 * Single Arduino Standalone TTS v8 — 16kHz Clean Output
 * Plays all 24 phonemes directly from internal Flash memory.
 * No I2C, no Slaves, zero external hardware dependencies!
 */

#include <avr/pgmspace.h>
#include "phonemes.h"

#define MAX_TEXT    150
#define PLAY_HZ    16000

volatile uint8_t  tbuf[MAX_TEXT];
volatile uint8_t  tlen = 0, playing = 0, ph_idx = 0;
volatile uint16_t sp = 0;
volatile char     punc_mode = 'T'; // 'T' = statement, 'Q' = question, 'E' = exclamation
static   uint16_t cur_off, cur_len;
static   uint16_t nxt_off, nxt_len;
static   uint8_t  frame_ct = 0;
static   uint8_t  prev_s = 128;

static void prep_next() {
  if (ph_idx >= tlen) { cur_off=0xFFFF; cur_len=0; nxt_off=0xFFFF; nxt_len=0; return; }
  uint8_t ph = tbuf[ph_idx];
  if (ph >= PHONEME_COUNT) ph = PH_SPACE;
  cur_off = pgm_read_word(&ph_off[ph]);
  cur_len = pgm_read_word(&ph_len[ph]);
  nxt_off = 0xFFFF; nxt_len = 0;
  if (ph_idx + 1 < tlen) {
    uint8_t n = tbuf[ph_idx + 1];
    if (n < PHONEME_COUNT) {
      nxt_off = pgm_read_word(&ph_off[n]);
      nxt_len = pgm_read_word(&ph_len[n]);
    }
  }
}

static void basla() {
  cli();
  ph_idx = 0; sp = 0; frame_ct = 0; prev_s = 128;
  prep_next();
  playing = (tlen > 0);
  sei();
}

void setup() {
  // Timer 2: High-speed PWM Carrier on Pin 3 and Pin 11
  pinMode(3, OUTPUT);
  pinMode(11, OUTPUT);
  TCCR2A = _BV(COM2A1) | _BV(COM2B1) | _BV(WGM21) | _BV(WGM20);
  TCCR2B = _BV(CS20); // Prescaler = 1 (62.5kHz carrier frequency)
  OCR2A = 128; OCR2B = 128;

  // Timer 1: Precise 16kHz Audio Sample Rate Trigger
  cli();
  TCCR1A = 0; TCCR1B = 0; TCNT1 = 0;
  OCR1A  = (F_CPU / PLAY_HZ) - 1; // 999 for 16kHz at 16MHz clock
  TCCR1B = _BV(WGM12) | _BV(CS10); // CTC Mode, Prescaler = 1
  TIMSK1 = _BV(OCIE1A); // Enable Compare Match Interrupt
  sei();

  Serial.begin(9600);
  Serial.println(F("Single Board TTS v8 16kHz (9600 Baud)"));
}

static uint8_t utf8_state;

void loop() {
  static char buf[160];
  static int  p = 0;
  while (Serial.available()) {
    uint8_t uc = (uint8_t)Serial.read();
    char c = (char)uc;
    if (utf8_state == 1) {
      utf8_state = 0;
      if      (uc==0xA7) c='c'; else if (uc==0x87) c='C';
      else if (uc==0xB6) c='o'; else if (uc==0x96) c='O';
      else if (uc==0xBC) c='u'; else if (uc==0x9C) c='U';
      else continue;
    } else if (utf8_state == 2) {
      utf8_state = 0;
      if      (uc==0x9F) c='g'; else if (uc==0x9E) c='G';
      else if (uc==0xB1) c='i'; else if (uc==0xB0) c='I';
      else continue;
    } else if (utf8_state == 3) {
      utf8_state = 0;
      if      (uc==0x9F) c='s'; else if (uc==0x9E) c='S';
      else continue;
    } else if (uc==0xC3) { utf8_state=1; continue; }
      else if (uc==0xC4) { utf8_state=2; continue; }
      else if (uc==0xC5) { utf8_state=3; continue; }

    if (c == '\n') {
      if (p > 0) {
        buf[p] = 0;
        
        // Strip trailing spaces & detect punctuation mode
        char punc = 'T'; 
        int last_char_idx = p - 1;
        while (last_char_idx >= 0 && (buf[last_char_idx] == ' ' || buf[last_char_idx] == '\r')) {
          last_char_idx--;
        }
        if (last_char_idx >= 0) {
          char lc = buf[last_char_idx];
          if (lc == '?') { punc = 'Q'; buf[last_char_idx] = ' '; }
          else if (lc == '!') { punc = 'E'; buf[last_char_idx] = ' '; }
          else if (lc == '.') { punc = 'T'; buf[last_char_idx] = ' '; }
        }

        cli();
        int idx = 0;
        for (int i = 0; i < p && idx < MAX_TEXT; i++) {
          char ch = buf[i];
          if (ch >= 'A' && ch <= 'Z') ch += 32;
          if (ch >= 0 && ch < 128)
            tbuf[idx++] = pgm_read_byte(&c2p[(uint8_t)ch]);
        }
        // Append spaces for natural pause
        if (idx < MAX_TEXT) tbuf[idx++] = 23; // SPACE phoneme index
        if (idx < MAX_TEXT) tbuf[idx++] = 23;
        
        tlen = idx;
        punc_mode = punc;
        sei();
        
        basla();
        Serial.print(F("-> ")); Serial.println(buf);
      }
      p = 0;
    } else if (c != '\r' && p < 159) buf[p++] = c;
  }
}

ISR(TIMER1_COMPA_vect) {
  static uint16_t slide_counter = 0;
  if (!playing || ph_idx >= tlen) {
    slide_counter = 0;
    OCR2A = 128; OCR2B = 128; playing = 0; return;
  }

  // Adjust playback pitch dynamically based on punctuation mode (at 16kHz base = 999)
  if (punc_mode == 'E') {
    OCR1A = 900; // ~10% faster and higher pitch for exclamations!
  } else if (punc_mode == 'Q' && tlen >= 4 && ph_idx >= (tlen - 4)) {
    // Soru (?) pitch rise slide (smooth glide up)
    uint16_t drop = slide_counter >> 6;
    if (drop > 150) drop = 150;
    OCR1A = 999 - drop; 
    slide_counter++;
  } else if (punc_mode == 'T' && tlen >= 4 && ph_idx >= (tlen - 4)) {
    // Statement drop slide (smooth glide down)
    uint16_t rise = slide_counter >> 7;
    if (rise > 75) rise = 75;
    OCR1A = 999 + rise; 
    slide_counter++;
  } else {
    slide_counter = 0;
    OCR1A = 999; // Standard 16kHz pitch
  }

  uint8_t s = 128;
  if (cur_off != 0xFFFF) {
    s = pgm_read_byte(&pcm[cur_off + sp]);
  }

  // Crossfade (Smoothly fade between phonemes)
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

  // Output sample
  OCR2A = s;
  OCR2B = s;

  sp++;
  if (sp >= cur_len) {
    ph_idx++; sp = 0;
    if (ph_idx >= tlen) { OCR2A=128; OCR2B=128; playing=0; }
    else prep_next();
  }
}
