#!/usr/bin/env python3
import sys
import os
import wave
import numpy as np

# Try to import serial for Arduino communication
try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

# Import phoneme generator from local directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    import generate_phonemes
except ImportError:
    print("[!] HATA: 'generate_phonemes.py' dosyası bulunamadı. Lütfen bu betiği proje klasöründe çalıştırın.")
    sys.exit(1)

# Turkish character mapping to match Arduino UTF-8 decoding
TURKISH_MAP = {
    'ç': 'c', 'Ç': 'C',
    'ğ': 'g', 'Ğ': 'G',
    'ı': 'i', 'İ': 'I',
    'ö': 'o', 'Ö': 'O',
    'ş': 's', 'Ş': 'S',
    'ü': 'u', 'Ü': 'U'
}

def clean_text(text):
    # Convert Turkish specific characters to ASCII equivalents
    cleaned = ""
    for char in text:
        cleaned += TURKISH_MAP.get(char, char)
    return cleaned

def text_to_phonemes(text):
    cleaned = clean_text(text)
    # Strip final punctuation for mode detection
    punc_mode = 'T'
    if cleaned.endswith('?'):
        punc_mode = 'Q'
        cleaned = cleaned[:-1] + ' '
    elif cleaned.endswith('!'):
        punc_mode = 'E'
        cleaned = cleaned[:-1] + ' '
    elif cleaned.endswith('.'):
        punc_mode = 'T'
        cleaned = cleaned[:-1] + ' '
        
    phoneme_list = []
    # Map chars to phonemes
    mapping = {
        'a': 'A', 'b': 'B', 'c': 'C', 'd': 'D', 'e': 'E', 'f': 'F',
        'g': 'G', 'h': 'H', 'i': 'I', 'j': 'J', 'k': 'K', 'l': 'L',
        'm': 'M', 'n': 'N', 'o': 'O', 'p': 'P', 'r': 'R', 's': 'S',
        't': 'T', 'u': 'U', 'v': 'V', 'y': 'Y', 'z': 'Z', ' ': 'SPACE'
    }
    
    for char in cleaned.lower():
        if char in mapping:
            phoneme_list.append(mapping[char])
            
    # Add trailing spaces for natural pause
    phoneme_list.append('SPACE')
    phoneme_list.append('SPACE')
    
    return phoneme_list, punc_mode

def compile_audio(phoneme_list, phonemes_dict):
    SR = generate_phonemes.SR
    CROSSFADE = generate_phonemes.CROSSFADE
    
    audio_chunks = []
    
    for i, ph_name in enumerate(phoneme_list):
        if ph_name in phonemes_dict:
            # Convert 0-255 uint8 back to float (-1.0 to 1.0)
            chunk = (phonemes_dict[ph_name].astype(np.float64) - 128.0) / 127.0
            audio_chunks.append(chunk)
        else:
            # Silence chunk
            audio_chunks.append(np.zeros(1000))
            
    if not audio_chunks:
        return np.array([], dtype=np.uint8)
        
    # Crossfade mixer
    mixed = audio_chunks[0].copy()
    for i in range(1, len(audio_chunks)):
        curr_chunk = audio_chunks[i].copy()
        if len(mixed) > CROSSFADE and len(curr_chunk) > CROSSFADE:
            # Smooth crossfade overlap
            fade_out = np.linspace(1.0, 0.0, CROSSFADE)
            fade_in = np.linspace(0.0, 1.0, CROSSFADE)
            
            # Mix the overlapping regions
            mixed[-CROSSFADE:] = mixed[-CROSSFADE:] * fade_out + curr_chunk[:CROSSFADE] * fade_in
            # Append the rest
            mixed = np.concatenate([mixed, curr_chunk[CROSSFADE:]])
        else:
            mixed = np.concatenate([mixed, curr_chunk])
            
    # Normalize and convert back to 8-bit PCM (or 16-bit for WAV)
    mx = np.max(np.abs(mixed))
    if mx > 0:
        mixed = mixed / mx * 0.9  # Headroom
        
    # Convert to 16-bit signed PCM for standard WAV
    pcm16 = (mixed * 32767).astype(np.int16)
    return pcm16

def save_wav(filename, pcm16_data, sr=24000):
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(1)      # Mono
        wf.setsampwidth(2)      # 16-bit (2 bytes)
        wf.setframerate(sr)     # 24kHz (or matches SR)
        wf.writeframes(pcm16_data.tobytes())
    print(f"[+] Ses başarıyla PC'ye kaydedildi: {filename}")

def main():
    if len(sys.argv) < 2:
        print("Kullanım: python3 speak.py \"Söylenecek cümle buraya yazılır.\"")
        sys.exit(1)
        
    text = sys.argv[1]
    
    print("-" * 50)
    print(f"Metin: {text}")
    
    # 1. Generate phonemes and compile WAV
    print("[*] Ses sentezleniyor...")
    np.random.seed(42)
    phonemes_dict = generate_phonemes.generate_all()
    phoneme_list, punc_mode = text_to_phonemes(text)
    pcm_data = compile_audio(phoneme_list, phonemes_dict)
    
    output_filename = "kayit.wav"
    save_wav(output_filename, pcm_data, generate_phonemes.SR)
    
    # 2. Send to physical Arduino Master if connected
    if HAS_SERIAL:
        # Check if user specified a port as the second argument (e.g. python3 speak.py "text" /dev/ttyUSB1)
        user_port = None
        if len(sys.argv) > 2:
            user_port = sys.argv[2]
            
        # Prioritize ttyUSB1 based on user's hardware configuration
        ports = ["/dev/ttyUSB1", "/dev/ttyUSB0", "/dev/ttyUSB2", "/dev/ttyACM0"]
        if user_port:
            ports = [user_port] + [p for p in ports if p != user_port]
            
        arduino = None
        for p in ports:
            if os.path.exists(p):
                try:
                    # Arduino Master baud rate is 9600
                    arduino = serial.Serial(p, 9600, timeout=1)
                    print(f"[+] Arduino Master bağlandı: {p}")
                    break
                except Exception as e:
                    print(f"[!] Uyarı: {p} portu açılamadı. Detay: {e}")
                    print("    (Eğer cihaz meşgulse, Arduino Serial Monitor / IDE ekranını kapatın!)")
                    continue
                    
        if arduino:
            import time
            print("[*] Arduino'nun hazır olması bekleniyor (Handshake)...")
            
            # Read from serial until we see the Arduino's boot message
            booted = False
            start_time = time.time()
            while time.time() - start_time < 5.0: # 5 second timeout
                if arduino.in_waiting > 0:
                    line = arduino.readline().decode('utf-8', errors='ignore')
                    if "Master" in line or "TTS" in line:
                        booted = True
                        break
                time.sleep(0.05)
                
            if not booted:
                print("[!] Başlangıç mesajı alınamadı (Zaman aşımı), kör bekleme yapılıyor...")
                time.sleep(2.0)
            else:
                print("[+] Arduino başarıyla hazırlandı!")
                
            # Send text to Arduino (ending with newline)
            print("[*] Metin gönderiliyor ve Arduino konuşturuluyor...")
            arduino.write((text + "\n").encode('utf-8'))
            arduino.flush()
            
            # Keep serial port open during playback to prevent DTR reset!
            print("[*] Hoparlörden çalınması bekleniyor (lütfen bekleyin)...")
            duration = max(3.0, len(text) * 0.16) # Estimate play duration
            time.sleep(duration)
            arduino.close()
        else:
            print("[!] Bilgi: Bağlı Arduino Master bulunamadı. Sadece PC'ye ses kaydedildi.")
    else:
        print("[!] Bilgi: 'pyserial' modülü kurulu değil. Arduino'ya otomatik gönderim yapılmadı.")
        print("    Kurmak için: pip install pyserial")
        
    print("-" * 50)

if __name__ == "__main__":
    main()
