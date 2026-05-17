/*
 * AI Master TTS v8 — 32kHz Clean Output
 * PCM data is already high quality, DSP kept minimal and clean
 */

#include <Wire.h>
#include <avr/pgmspace.h>
#include "phonemes.h"

#define SLAVE_ADDR   8
#define SLAVE2_ADDR  9
#define MAX_TEXT    300
#define PLAY_HZ    32000

volatile uint8_t  tbuf[MAX_TEXT];
volatile uint8_t  tlen = 0, playing = 0, ph_idx = 0;
volatile uint16_t sp = 0;
volatile char     punc_mode = 'T'; // 'T' = statement, 'Q' = question, 'E' = exclamation
static   uint16_t cur_off, cur_len;
static   uint16_t nxt_off, nxt_len;
static   bool     odd_sample = false;
static   uint8_t  mid_s = 128;

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
  ph_idx = 0; sp = 0; odd_sample = false; mid_s = 128;
  prep_next();
  playing = (tlen > 0);
  sei();
}

void setup() {
  pinMode(3, OUTPUT);
  pinMode(11, OUTPUT);
  TCCR2A = _BV(COM2A1) | _BV(COM2B1) | _BV(WGM21) | _BV(WGM20);
  TCCR2B = _BV(CS20);
  OCR2A = 128; OCR2B = 128;

  cli();
  TCCR1A = 0; TCCR1B = 0; TCNT1 = 0;
  OCR1A  = (F_CPU / (2 * PLAY_HZ)) - 1;
  TCCR1B = _BV(WGM12) | _BV(CS10);
  TIMSK1 = _BV(OCIE1A);
  sei();

  Wire.begin();
  Wire.setClock(100000); // 100kHz standard I2C Mode (highly stable over breadboard jumpers)
#if defined(ARDUINO_ARCH_AVR)
  Wire.setWireTimeout(3000, true); // Enable automatic I2C recovery on timeout
#endif
  Serial.begin(9600);
  Serial.println(F("Master TTS v8 32kHz (9600 Baud)"));
}

static uint8_t utf8_state;

void loop() {
  static char buf[310];
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
        // Append single space for natural pause
        if (idx < MAX_TEXT) tbuf[idx++] = 23; // SPACE phoneme index
        
        tlen = idx;
        punc_mode = punc;
        sei();
        
        // Send to Slave 1 (retrying silently, abort if fully dead)
        int sent = 0;
        bool ok = true;
        while (sent < tlen && ok) {
          int retries = 3;
          byte err = 1;
          int chunk = tlen - sent;
          if (chunk > 24) chunk = 24; // Safe chunk size (24 + 1 cmd = 25 bytes, well below 32-byte I2C buffer)
          while (retries > 0 && err != 0) {
            Wire.beginTransmission(SLAVE_ADDR);
            Wire.write(sent == 0 ? punc : 'C');
            for (int i = 0; i < chunk; i++) {
              Wire.write(tbuf[sent + i]);
            }
            err = Wire.endTransmission();
            if (err != 0) { delay(5); retries--; } // 5ms delay on error retry
          }
          if (err == 0) {
            sent += chunk;
            delay(10); // 10ms delay between successful chunks gives Slave plenty of time to process
          } else { ok = false; }
        }

        // Send to Slave 2 (retrying silently, abort if fully dead)
        sent = 0;
        while (sent < tlen && ok) {
          int retries = 3;
          byte err = 1;
          int chunk = tlen - sent;
          if (chunk > 24) chunk = 24; // Safe chunk size
          while (retries > 0 && err != 0) {
            Wire.beginTransmission(SLAVE2_ADDR);
            Wire.write(sent == 0 ? punc : 'C');
            for (int i = 0; i < chunk; i++) {
              Wire.write(tbuf[sent + i]);
            }
            err = Wire.endTransmission();
            if (err != 0) { delay(5); retries--; } // 5ms delay on error retry
          }
          if (err == 0) {
            sent += chunk;
            delay(10); // 10ms delay between successful chunks
          } else { ok = false; }
        }

        if (ok) {
          // Send SYNC PLAY trigger to Slaves (retrying silently if needed)
          int retries = 3; byte err = 1;
          while (retries > 0 && err != 0) {
            Wire.beginTransmission(SLAVE_ADDR);
            Wire.write('S');
            err = Wire.endTransmission();
            if (err != 0) { delay(2); retries--; }
          }
          
          retries = 3; err = 1;
          while (retries > 0 && err != 0) {
            Wire.beginTransmission(SLAVE2_ADDR);
            Wire.write('S');
            err = Wire.endTransmission();
            if (err != 0) { delay(2); retries--; }
          }
          
          basla();
        }
        Serial.print(F("-> ")); Serial.println(buf);
      }
      p = 0;
    } else if (c != '\r' && p < 309) buf[p++] = c;
  }

  static uint8_t was_playing = 0;
  if (was_playing && !playing) {
    Serial.println(F("DONE"));
  }
  was_playing = playing;
}

ISR(TIMER1_COMPA_vect) {
  static uint16_t slide_counter = 0;
  if (!playing || ph_idx >= tlen) {
    slide_counter = 0;
    odd_sample = false;
    DDRD |= (1 << 3); // Set Pin 3 to OUTPUT (Maintain bias on Master)
    OCR2A = 128; OCR2B = 128; playing = 0; return;
  }

  // Adjust playback pitch dynamically based on punctuation mode (Fast Math without division)
  // Since we are running at 64kHz base rate:
  if (punc_mode == 'E') {
    OCR1A = 225; // ~10% faster (249 * 0.9 = 224 -> 225)
  } else if (punc_mode == 'Q' && tlen >= 4 && ph_idx >= (tlen - 4)) {
    // Soru (?) pitch rise slide (smooth across last 200ms)
    uint16_t drop = slide_counter >> 7; // Increment speed is doubled, so shift 1 more
    if (drop > 37) drop = 37;
    OCR1A = 249 - drop; // Glide up
    slide_counter++;
  } else if (punc_mode == 'T' && tlen >= 4 && ph_idx >= (tlen - 4)) {
    // Statement drop slide (smooth across last 200ms)
    uint16_t rise = slide_counter >> 8;
    if (rise > 20) rise = 20;
    OCR1A = 249 + rise; // Glide down
    slide_counter++;
  } else {
    slide_counter = 0;
    OCR1A = 249; // Standard 64kHz pitch (corresponds to 32kHz sample rate)
  }

  uint8_t output_val = 128;

  if (!odd_sample) {
    // 1. Fetch current sample
    uint8_t s = 128;
    if (cur_off != 0xFFFF) {
      s = pgm_read_byte(&pcm[cur_off + sp]);
    }

    // Apply crossfade if near the end of phoneme
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

    // 2. Fetch NEXT sample for interpolation
    uint8_t next_s = 128;
    if (sp + 1 < cur_len) {
      if (cur_off != 0xFFFF) {
        next_s = pgm_read_byte(&pcm[cur_off + sp + 1]);
      }
      
      // Crossfade logic for the next sample too to keep interpolation seamless
      uint16_t next_sp = sp + 1;
      if (cur_len > CROSSFADE_SAMPLES && next_sp >= (cur_len - CROSSFADE_SAMPLES)) {
        uint16_t fade = next_sp - (cur_len - CROSSFADE_SAMPLES);
        uint16_t target_len = (nxt_len > 0) ? nxt_len : CROSSFADE_SAMPLES;
        if (fade < target_len) {
          uint8_t ns = 128;
          if (nxt_off != 0xFFFF && nxt_len > 0) {
            ns = pgm_read_byte(&pcm[nxt_off + fade]);
          }
          next_s = ((uint16_t)next_s * (CROSSFADE_SAMPLES - fade) + (uint16_t)ns * fade) / CROSSFADE_SAMPLES;
        }
      }
    } else {
      // Transition to next phoneme
      if (nxt_off != 0xFFFF && nxt_len > 0) {
        next_s = pgm_read_byte(&pcm[nxt_off]);
      }
    }

    // Calculate mid-point
    mid_s = ((uint16_t)s + next_s) >> 1;
    output_val = s;
    odd_sample = true;

  } else {
    // Output the interpolated mid-point and increment sample pointer
    output_val = mid_s;
    odd_sample = false;

    sp++;
    if (sp >= cur_len) {
      ph_idx++; sp = 0;
      if (ph_idx >= tlen) { OCR2A = 128; OCR2B = 128; playing = 0; }
      else prep_next();
    }
  }

  // ALWAYS output the sample (active or crossfaded silence).
  // This puts the three 1K resistors in parallel (333 Ohms), fixing the extreme lowpass muffling!
  DDRD |= (1 << 3); 
  OCR2A = output_val;
  OCR2B = output_val;
}
