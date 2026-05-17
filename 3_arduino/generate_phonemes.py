#!/usr/bin/env python3
"""
Turkish TTS Phoneme Generator v3 — Dual Core 24kHz
Splits phonemes perfectly into two buckets for Master and Slave Arduinos
"""
import numpy as np
import os

SR = 24000
CROSSFADE = 192

def make_glottal(n, f0_start=140, f0_end=130):
    t = np.arange(n, dtype=np.float64) / SR
    f0_contour = np.linspace(f0_start, f0_end, n)
    phase = np.cumsum(f0_contour) / SR
    phase = phase % 1.0
    pulse = np.zeros(n)
    mask_open = phase < 0.6
    p_open = phase[mask_open] / 0.6
    pulse[mask_open] = 3*p_open**2 - 2*p_open**3
    mask_close = (phase >= 0.6) & (phase < 0.8)
    p_close = (phase[mask_close] - 0.6) / 0.2
    pulse[mask_close] = 1.0 - p_close**2
    jitter = 1.0 + np.random.randn(n) * 0.005
    pulse *= jitter
    return pulse

def biquad_resonator(sig, fc, bw, sr=SR):
    w0 = 2 * np.pi * fc / sr
    alpha = np.sin(w0) * np.sinh(np.log(2)/2 * bw/fc * w0/np.sin(w0)) if fc > 0 else 0.01
    b0 = alpha; b1 = 0.0; b2 = -alpha
    a0 = 1 + alpha; a1 = -2 * np.cos(w0); a2 = 1 - alpha
    b0 /= a0; b1 /= a0; b2 /= a0; a1 /= a0; a2 /= a0
    out = np.zeros(len(sig))
    x1 = x2 = y1 = y2 = 0.0
    for i in range(len(sig)):
        x0 = sig[i]
        y0 = b0*x0 + b1*x1 + b2*x2 - a1*y1 - a2*y2
        x2, x1 = x1, x0
        y2, y1 = y1, y0
        out[i] = y0
    return out

def lowpass(sig, fc, sr=SR):
    rc = 1.0 / (2 * np.pi * fc)
    dt = 1.0 / sr
    a = dt / (rc + dt)
    out = np.zeros(len(sig))
    out[0] = sig[0] * a
    for i in range(1, len(sig)):
        out[i] = out[i-1] + a * (sig[i] - out[i-1])
    return out

def pre_emphasis(sig, alpha=0.85):
    out = np.zeros(len(sig))
    out[0] = sig[0]
    for i in range(1, len(sig)):
        out[i] = sig[i] - alpha * sig[i-1]
    return out

def envelope(n, att_ms=5, hold_ratio=0.7, rel_ms=15):
    env = np.ones(n)
    att = max(int(att_ms * SR / 1000), 1)
    rel = max(int(rel_ms * SR / 1000), 1)
    hold_end = int(n * hold_ratio)
    if att < n: env[:att] = np.linspace(0, 1, att)
    if rel < n - hold_end: env[hold_end:] = np.linspace(1, 0, n - hold_end)
    return env

def anti_hardware_filter(sig, fc=3200, sr=SR):
    rc = 1.0 / (2 * np.pi * fc)
    dt = 1.0 / sr
    a = rc / (rc + dt)
    out = np.zeros_like(sig)
    out[0] = sig[0]
    out[1:] = (sig[1:] - a * sig[:-1]) / (1.0 - a)
    return out

def to_pcm8(sig, target_peak=0.85):
    sig = anti_hardware_filter(sig, fc=3200)
    mx = np.max(np.abs(sig))
    if mx < 1e-10: return np.full(len(sig), 128, dtype=np.uint8)
    sig = sig / mx * target_peak
    return np.round(sig * 127 + 128).clip(0, 255).astype(np.uint8)

VOWELS = {
    'a': (750,  60, 1200, 70, 2600, 100, 150),
    'e': (500,  50, 1800, 60, 2500,  90, 150),
    'i': (280,  40, 2250, 60, 2900,  80, 150),
    'o': (500,  50,  850, 60, 2600, 100, 150),
    'u': (320,  40,  750, 50, 2500,  90, 150),
}

def gen_vowel(f1, bw1, f2, bw2, f3, bw3, dur_ms):
    n = int(SR * dur_ms / 1000)
    src = make_glottal(n, f0_start=145, f0_end=130)
    r1 = biquad_resonator(src, f1, bw1)
    r2 = biquad_resonator(src, f2, bw2)
    r3 = biquad_resonator(src, f3, bw3)
    out = r1 * 1.0 + r2 * 0.5 + r3 * 0.2
    breath = np.random.randn(n) * 0.03
    out += lowpass(breath, f1 * 1.5)
    out *= envelope(n, 8, 0.75, 15)
    out = pre_emphasis(out, 0.6)
    return to_pcm8(out, 0.90)

def gen_plosive(burst_f, aspiration_f, dur_ms, voiced=False):
    n = int(SR * dur_ms / 1000)
    closure = int(n * 0.25)
    burst = int(n * 0.15)
    aspiration = n - closure - burst
    parts = []
    if voiced:
        src = make_glottal(closure, 130, 130) * 0.15
        c = lowpass(src, 200)
    else: c = np.zeros(closure)
    parts.append(c)
    b = np.random.randn(burst) * 0.8
    b = biquad_resonator(b, burst_f, burst_f * 0.5)
    b *= np.linspace(1, 0.3, burst)
    parts.append(b)
    if voiced:
        a = make_glottal(aspiration, 130, 130) * 0.5
        a += np.random.randn(aspiration) * 0.15
        a = biquad_resonator(a, aspiration_f, 200)
    else:
        a = np.random.randn(aspiration) * 0.4
        a = biquad_resonator(a, aspiration_f, 300)
    a *= np.linspace(0.8, 0, aspiration)
    parts.append(a)
    out = np.concatenate(parts)
    out = pre_emphasis(out, 0.8)
    return to_pcm8(out, 0.50)

def gen_fricative(center_f, bandwidth, dur_ms, voiced=False):
    n = int(SR * dur_ms / 1000)
    noise = np.random.randn(n)
    fric = biquad_resonator(noise, center_f, bandwidth)
    if voiced:
        voice = make_glottal(n, 130, 130) * 0.3
        voice = lowpass(voice, 500)
        fric = fric * 0.7 + voice
    fric *= envelope(n, 5, 0.8, 8)
    fric = pre_emphasis(fric, 0.8)
    return to_pcm8(fric, 0.40)

def gen_nasal(nasal_f, oral_f, dur_ms):
    n = int(SR * dur_ms / 1000)
    src = make_glottal(n, 135, 130)
    nasal = biquad_resonator(src, nasal_f, 50)
    oral = biquad_resonator(src, oral_f, 100) * 0.2
    anti = biquad_resonator(src, 1000, 200) * 0.15
    out = nasal + oral - anti
    out *= envelope(n, 10, 0.75, 12)
    out = pre_emphasis(out, 0.5)
    return to_pcm8(out, 0.60)

def gen_liquid(f1, f2, dur_ms):
    n = int(SR * dur_ms / 1000)
    src = make_glottal(n, 135, 130)
    out = np.zeros(n)
    seg_size = 128
    for i in range(0, n, seg_size):
        end = min(i + seg_size, n)
        seg = src[i:end]
        progress = (i + seg_size//2) / n
        f2_now = f2 * (0.6 + 0.4 * progress)
        r1 = biquad_resonator(seg, f1, 60)
        r2 = biquad_resonator(seg, f2_now, 80) * 0.4
        out[i:end] = r1 + r2
    out *= envelope(n, 8, 0.7, 15)
    out = pre_emphasis(out, 0.5)
    return to_pcm8(out, 0.70)

def gen_trill(f1, f2, dur_ms):
    n = int(SR * dur_ms / 1000)
    src = make_glottal(n, 130, 130)
    t = np.arange(n, dtype=np.float64) / SR
    mod = 0.5 + 0.5 * np.sin(2 * np.pi * 28 * t)
    src *= mod
    r1 = biquad_resonator(src, f1, 70)
    r2 = biquad_resonator(src, f2, 90) * 0.35
    out = r1 + r2
    out *= envelope(n, 5, 0.7, 10)
    out = pre_emphasis(out, 0.6)
    return to_pcm8(out, 0.75)

def gen_glide(f1, f2_start, f2_end, dur_ms):
    n = int(SR * dur_ms / 1000)
    src = make_glottal(n, 135, 130)
    out = np.zeros(n)
    seg_size = 128
    for i in range(0, n, seg_size):
        end = min(i + seg_size, n)
        seg = src[i:end]
        progress = (i + seg_size//2) / n
        f2_now = f2_start + (f2_end - f2_start) * progress
        r1 = biquad_resonator(seg, f1, 60)
        r2 = biquad_resonator(seg, f2_now, 80) * 0.5
        out[i:end] = r1 + r2
    out *= envelope(n, 10, 0.7, 15)
    out = pre_emphasis(out, 0.5)
    return to_pcm8(out, 0.80)

def gen_affricate(burst_f, fric_f, dur_ms, voiced=False):
    n = int(SR * dur_ms / 1000)
    stop_n = int(n * 0.35)
    fric_n = n - stop_n
    stop = np.zeros(stop_n)
    burst_start = int(stop_n * 0.6)
    burst_data = np.random.randn(stop_n - burst_start) * 0.6
    burst_data = biquad_resonator(burst_data, burst_f, burst_f * 0.4)
    stop[burst_start:] = burst_data
    noise = np.random.randn(fric_n)
    fric = biquad_resonator(noise, fric_f, fric_f * 0.3)
    if voiced:
        voice = make_glottal(fric_n, 130, 130) * 0.25
        fric = fric * 0.7 + lowpass(voice, 400)
    fric *= envelope(fric_n, 3, 0.7, 10)
    out = np.concatenate([stop, fric])
    out = pre_emphasis(out, 0.8)
    return to_pcm8(out, 0.55)

def gen_silence(dur_ms):
    return np.full(int(SR * dur_ms / 1000), 128, dtype=np.uint8)

def generate_all():
    phonemes = {}
    for ch, (f1,bw1,f2,bw2,f3,bw3,dur) in VOWELS.items():
        phonemes[ch.upper()] = gen_vowel(f1,bw1,f2,bw2,f3,bw3,dur)
    phonemes['B'] = gen_plosive(400, 800, 75, voiced=True)
    phonemes['C'] = gen_affricate(400, 2500, 80, voiced=False)
    phonemes['D'] = gen_plosive(400, 1700, 75, voiced=True)
    phonemes['F'] = gen_fricative(2500, 1500, 75, voiced=False)
    phonemes['G'] = gen_plosive(300, 1200, 75, voiced=True)
    phonemes['H'] = gen_fricative(1500, 3000, 70, voiced=False)
    phonemes['J'] = gen_affricate(300, 2200, 80, voiced=True)
    phonemes['K'] = gen_plosive(400, 1500, 70, voiced=False)
    phonemes['L'] = gen_liquid(350, 1100, 85)
    phonemes['M'] = gen_nasal(280, 900, 85)
    phonemes['N'] = gen_nasal(280, 1500, 85)
    phonemes['P'] = gen_plosive(500, 1200, 70, voiced=False)
    phonemes['R'] = gen_trill(350, 1300, 80)
    phonemes['S'] = gen_fricative(4500, 2000, 75, voiced=False)
    phonemes['T'] = gen_plosive(500, 1800, 70, voiced=False)
    phonemes['V'] = gen_fricative(800, 600, 75, voiced=True)
    phonemes['Y'] = gen_glide(280, 2400, 1800, 85)
    phonemes['Z'] = gen_fricative(3500, 1500, 75, voiced=True)
    phonemes['SPACE'] = gen_silence(80)
    return phonemes

def write_header(phonemes, dname, node_idx, total_nodes=3):
    order = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','R','S','T','U','V','Y','Z','SPACE']
    
    # Perfect memory balancing for N nodes
    buckets = [set() for _ in range(total_nodes)]
    lengths_arr = [0] * total_nodes
    sorted_keys = sorted(order, key=lambda x: len(phonemes[x]), reverse=True)
    for k in sorted_keys:
        idx = lengths_arr.index(min(lengths_arr))
        buckets[idx].add(k)
        lengths_arr[idx] += len(phonemes[k])
        
    my_keys = buckets[node_idx]

    offsets = []
    lengths = []
    pcm_data = []
    off = 0
    
    for i, n in enumerate(order):
        length = len(phonemes[n])
        lengths.append(length)
        if n in my_keys:
            offsets.append(off)
            pcm_data.append(phonemes[n])
            off += length
        else:
            offsets.append(0xFFFF)
    
    if pcm_data:
        all_pcm = np.concatenate(pcm_data)
    else:
        all_pcm = np.array([128], dtype=np.uint8)
        
    total = len(all_pcm)
    node_name = f"NODE {node_idx}"
    if node_idx == 0: node_name = "MASTER"
    elif node_idx == 1: node_name = "SLAVE 1"
    elif node_idx == 2: node_name = "SLAVE 2"
    print(f"[{node_name}] PCM: {total} bytes ({total/1024:.1f}KB)")
    
    # Create directory if it doesn't exist
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), dname)
    os.makedirs(out_dir, exist_ok=True)
    filename = os.path.join(out_dir, 'phonemes.h')
    
    with open(filename, 'w') as f:
        f.write("// phonemes.h — 3-Node 24kHz Turkish TTS\n")
        f.write(f"// {node_name}\n\n")
        f.write("#ifndef PHONEMES_H\n#define PHONEMES_H\n\n")
        f.write("#include <avr/pgmspace.h>\n\n")
        f.write(f"#define PHONEME_COUNT {len(order)}\n")
        f.write(f"#define SAMPLE_RATE   {SR}\n")
        f.write(f"#define CROSSFADE_SAMPLES {CROSSFADE}\n\n")
        
        for i, n in enumerate(order):
            f.write(f"#define PH_{n:6s}  {i}\n")
        
        f.write("\nconst uint16_t ph_off[PHONEME_COUNT] PROGMEM = {\n  ")
        f.write(",".join(f"0x{o:04X}" for o in offsets))
        f.write("\n};\n\nconst uint16_t ph_len[PHONEME_COUNT] PROGMEM = {\n  ")
        f.write(",".join(str(l) for l in lengths))
        f.write("\n};\n\n")

        # c2p mapping
        c2p = [23] * 128
        mapping = {'a':0,'b':1,'c':2,'d':3,'e':4,'f':5,'g':6,'h':7,
                   'i':8,'j':9,'k':10,'l':11,'m':12,'n':13,'o':14,'p':15,
                   'r':16,'s':17,'t':18,'u':19,'v':20,'y':21,'z':22}
        for ch, idx in mapping.items():
            c2p[ord(ch)] = idx
            c2p[ord(ch.upper())] = idx
        f.write("const unsigned char c2p[128] PROGMEM = {\n")
        for row in range(8):
            vals = c2p[row*16:(row+1)*16]
            f.write("  " + ",".join(f"{v:2d}" for v in vals))
            f.write(",\n" if row < 7 else "\n")
        f.write("};\n\n")

        f.write(f"const unsigned char pcm[{total}] PROGMEM = {{\n")
        for i in range(0, total, 16):
            chunk = all_pcm[i:i+16]
            line = ",".join(f"{v:3d}" for v in chunk)
            if i + 16 < total: line += ","
            f.write(f"  {line}\n")
        f.write("};\n\n#endif\n")

def generate_all_optimized(sr=16000):
    global SR, CROSSFADE
    SR = sr
    CROSSFADE = 128
    
    # Optimized short durations for fast, fluent, natural Turkish speech
    vowel_dur = 110 # ms
    plosive_dur = 55 # ms
    fricative_dur = 55 # ms
    nasal_dur = 65 # ms
    liquid_dur = 65 # ms
    trill_dur = 60 # ms
    glide_dur = 65 # ms
    affricate_dur = 60 # ms
    silence_dur = 60 # ms
    
    phonemes = {}
    for ch, (f1, bw1, f2, bw2, f3, bw3, _) in VOWELS.items():
        phonemes[ch.upper()] = gen_vowel(f1, bw1, f2, bw2, f3, bw3, vowel_dur)
        
    phonemes['B'] = gen_plosive(400, 800, plosive_dur, voiced=True)
    phonemes['C'] = gen_affricate(400, 2500, affricate_dur, voiced=False)
    phonemes['D'] = gen_plosive(400, 1700, plosive_dur, voiced=True)
    phonemes['F'] = gen_fricative(2500, 1500, fricative_dur, voiced=False)
    phonemes['G'] = gen_plosive(300, 1200, plosive_dur, voiced=True)
    phonemes['H'] = gen_fricative(1500, 3000, fricative_dur, voiced=False)
    phonemes['J'] = gen_affricate(300, 2200, affricate_dur, voiced=True)
    phonemes['K'] = gen_plosive(400, 1500, plosive_dur, voiced=False)
    phonemes['L'] = gen_liquid(350, 1100, liquid_dur)
    phonemes['M'] = gen_nasal(280, 900, nasal_dur)
    phonemes['N'] = gen_nasal(280, 1500, nasal_dur)
    phonemes['P'] = gen_plosive(500, 1200, plosive_dur, voiced=False)
    phonemes['R'] = gen_trill(350, 1300, trill_dur)
    phonemes['S'] = gen_fricative(4500, 2000, fricative_dur, voiced=False)
    phonemes['T'] = gen_plosive(500, 1800, plosive_dur, voiced=False)
    phonemes['V'] = gen_fricative(800, 600, fricative_dur, voiced=True)
    phonemes['Y'] = gen_glide(280, 2400, 1800, glide_dur)
    phonemes['Z'] = gen_fricative(3500, 1500, fricative_dur, voiced=True)
    phonemes['SPACE'] = gen_silence(silence_dur)
    return phonemes

def write_single_header(phonemes, dname):
    order = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','R','S','T','U','V','Y','Z','SPACE']
    
    offsets = []
    lengths = []
    pcm_data = []
    off = 0
    
    for n in order:
        length = len(phonemes[n])
        lengths.append(length)
        offsets.append(off)
        pcm_data.append(phonemes[n])
        off += length
        
    all_pcm = np.concatenate(pcm_data)
    total = len(all_pcm)
    print(f"[SINGLE BOARD] PCM: {total} bytes ({total/1024:.1f}KB)")
    
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), dname)
    os.makedirs(out_dir, exist_ok=True)
    filename = os.path.join(out_dir, 'phonemes.h')
    
    with open(filename, 'w') as f:
        f.write("// phonemes.h — Single-Board 16kHz Turkish TTS\n\n")
        f.write("#ifndef PHONEMES_H\n#define PHONEMES_H\n\n")
        f.write("#include <avr/pgmspace.h>\n\n")
        f.write(f"#define PHONEME_COUNT {len(order)}\n")
        f.write(f"#define SAMPLE_RATE   {SR}\n")
        f.write(f"#define CROSSFADE_SAMPLES {CROSSFADE}\n\n")
        
        for i, n in enumerate(order):
            f.write(f"#define PH_{n:6s}  {i}\n")
            
        f.write("\nconst uint16_t ph_off[PHONEME_COUNT] PROGMEM = {\n  ")
        f.write(",".join(f"0x{o:04X}" for o in offsets))
        f.write("\n};\n\nconst uint16_t ph_len[PHONEME_COUNT] PROGMEM = {\n  ")
        f.write(",".join(str(l) for l in lengths))
        f.write("\n};\n\n")
        
        # c2p mapping
        c2p = [23] * 128
        mapping = {'a':0,'b':1,'c':2,'d':3,'e':4,'f':5,'g':6,'h':7,
                   'i':8,'j':9,'k':10,'l':11,'m':12,'n':13,'o':14,'p':15,
                   'r':16,'s':17,'t':18,'u':19,'v':20,'y':21,'z':22}
        for ch, idx in mapping.items():
            c2p[ord(ch)] = idx
            c2p[ord(ch.upper())] = idx
        f.write("const unsigned char c2p[128] PROGMEM = {\n")
        for row in range(8):
            vals = c2p[row*16:(row+1)*16]
            f.write("  " + ",".join(f"{v:2d}" for v in vals))
            f.write(",\n" if row < 7 else "\n")
        f.write("};\n\n")
        
        f.write(f"const unsigned char pcm[{total}] PROGMEM = {{\n")
        for i in range(0, total, 16):
            chunk = all_pcm[i:i+16]
            line = ",".join(f"{v:3d}" for v in chunk)
            if i + 16 < total: line += ","
            f.write(f"  {line}\n")
        f.write("};\n\n#endif\n")

if __name__ == "__main__":
    np.random.seed(42)
    # Generate 32kHz 3-node headers (Legacy)
    print("Generating 3-Node 32kHz headers...")
    phonemes = generate_all()
    write_header(phonemes, 'ai_master', 0, 3)
    write_header(phonemes, 'ai_slave', 1, 3)
    write_header(phonemes, 'ai_slave_2', 2, 3)
    
    # Generate 16kHz Single-board header (Upgrade!)
    print("\nGenerating Single-Board 16kHz optimized header...")
    phonemes_opt = generate_all_optimized(16000)
    write_single_header(phonemes_opt, 'single_arduino_tts')

