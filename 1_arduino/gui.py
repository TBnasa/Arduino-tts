#!/usr/bin/env python3
import os
import re
import sys
import time
import glob
import threading
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox

# Import logic from speak.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    import speak
    import generate_phonemes
except ImportError:
    messagebox.showerror("Hata", "Lütfen bu dosyayı 'speak.py' ve 'generate_phonemes.py' dosyaları ile aynı klasörde çalıştırın.")
    sys.exit(1)

# Ensure 'sesler' directory exists
os.makedirs("sesler", exist_ok=True)

class TTSApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Arduino TTS Kontrol Paneli")
        self.root.geometry("520x440")
        self.root.resizable(False, False)
        
        # Style / Dark Mode Theme
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Colors
        self.bg_color = "#1E1E1E"
        self.fg_color = "#E0E0E0"
        self.accent_color = "#FF8C00"  # Orange accent
        self.btn_bg = "#333333"
        self.btn_active = "#444444"
        
        self.root.configure(bg=self.bg_color)
        
        # Apply custom widget styles
        self.style.configure('.', background=self.bg_color, foreground=self.fg_color)
        self.style.configure('TLabel', background=self.bg_color, foreground=self.fg_color, font=('Segoe UI', 10))
        self.style.configure('Title.TLabel', background=self.bg_color, foreground=self.accent_color, font=('Segoe UI', 15, 'bold'))
        self.style.configure('TButton', background=self.btn_bg, foreground=self.fg_color, font=('Segoe UI', 10, 'bold'), borderwidth=1)
        self.style.map('TButton', background=[('active', self.btn_active), ('pressed', self.accent_color)])
        self.style.configure('TCombobox', fieldbackground=self.btn_bg, background=self.btn_bg, foreground=self.fg_color)
        
        self.build_ui()
        self.refresh_ports()
        
    def build_ui(self):
        # 1. Title
        title_label = ttk.Label(self.root, text="🗣️ Arduino TTS Ses Sentezleyici", style="Title.TLabel")
        title_label.pack(pady=20)
        
        # 2. Text Input Frame
        input_frame = ttk.LabelFrame(self.root, text=" Söylenecek Cümle ")
        input_frame.pack(fill="x", padx=25, pady=10)
        
        # Beautiful, fully editable Entry widget
        self.text_entry = tk.Entry(
            input_frame, bg="#2D2D2D", fg="#FFFFFF", 
            insertbackground="#FFFFFF", relief="flat", font=('Segoe UI', 11)
        )
        self.text_entry.pack(fill="x", padx=15, pady=15, ipady=8)
        # Default placeholder text
        self.text_entry.insert(0, "Hava bugün sıcak, öyle değil mi Tahir?")
        
        # 3. Connection and Controls Frame
        ctrl_frame = ttk.Frame(self.root)
        ctrl_frame.pack(fill="x", padx=25, pady=10)
        
        ttk.Label(ctrl_frame, text="Arduino Portu:").grid(row=0, column=0, sticky="w", pady=5)
        
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(ctrl_frame, textvariable=self.port_var, width=25, state="readonly")
        self.port_combo.grid(row=0, column=1, padx=10, pady=5)
        
        refresh_btn = ttk.Button(ctrl_frame, text="🔄 Yenile", command=self.refresh_ports, width=8)
        refresh_btn.grid(row=0, column=2, padx=5, pady=5)
        
        # 4. Status Bar
        self.status_var = tk.StringVar(value="Hazır. Metin girip Çal'a basın.")
        self.status_label = ttk.Label(self.root, textvariable=self.status_var, font=('Segoe UI', 9, 'italic'), foreground="#AAAAAA")
        self.status_label.pack(pady=10)
        
        # 5. Play / Synthesize Button
        self.play_btn = ttk.Button(self.root, text="🗣️ Metni Sentezle ve Çal", command=self.start_synthesis)
        self.play_btn.pack(pady=15, ipadx=15, ipady=5)

    def refresh_ports(self):
        # Scan for ports
        found_ports = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
        
        # Add a fallback for just PC recording
        options = ["Yalnızca PC'ye Kaydet (WAV)"] + found_ports
        self.port_combo['values'] = options
        
        # Prioritize ttyUSB1 if it exists
        if "/dev/ttyUSB1" in found_ports:
            self.port_var.set("/dev/ttyUSB1")
        elif found_ports:
            self.port_var.set(found_ports[0])
        else:
            self.port_var.set("Yalnızca PC'ye Kaydet (WAV)")
            
        self.set_status("Port listesi yenilendi.")

    def set_status(self, text, color="#AAAAAA"):
        self.status_var.set(text)
        self.status_label.configure(foreground=color)

    def get_safe_filename(self, text):
        # Convert Turkish chars to standard ASCII equivalents
        cleaned = speak.clean_text(text)
        # Remove special characters
        cleaned = re.sub(r'[^a-zA-Z0-9 ]', '', cleaned)
        # Take first 4 words or timestamp
        words = cleaned.split()[:4]
        slug = "_".join(words).lower()
        if not slug:
            slug = f"ses_{int(time.time())}"
        return f"sesler/{slug}.wav"

    def start_synthesis(self):
        # Get text from entry widget
        text = self.text_entry.get().strip()
        if not text:
            messagebox.showwarning("Uyarı", "Lütfen boş metin girmeyin!")
            return
            
        # Disable button to prevent double clicking
        self.play_btn.state(["disabled"])
        self.set_status("Ses sentezleniyor...", self.accent_color)
        
        # Run in a background thread so the GUI does not freeze!
        thread = threading.Thread(target=self.run_tts_process, args=(text,))
        thread.daemon = True
        thread.start()

    def run_tts_process(self, text):
        try:
            # 1. Compile audio WAV
            np.random.seed(42)
            phonemes_dict = generate_phonemes.generate_all()
            phoneme_list, punc_mode = speak.text_to_phonemes(text)
            pcm_data = speak.compile_audio(phoneme_list, phonemes_dict)
            
            # Generate safe file name and save to 'sesler' folder
            output_filepath = self.get_safe_filename(text)
            speak.save_wav(output_filepath, pcm_data, generate_phonemes.SR)
            
            # 2. Arduino Communication
            selected_port = self.port_var.get()
            
            if selected_port != "Yalnızca PC'ye Kaydet (WAV)" and speak.HAS_SERIAL:
                import serial
                self.set_status("Arduino'ya bağlanılıyor...", self.accent_color)
                
                try:
                    arduino = serial.Serial(selected_port, 9600, timeout=1)
                    time.sleep(2.0) # Wait for reboot
                    
                    self.set_status("Metin gönderiliyor...", self.accent_color)
                    arduino.write((text + "\n").encode('utf-8'))
                    arduino.flush()
                    
                    # Estimate playback duration
                    duration = max(3.0, len(text) * 0.16)
                    
                    self.set_status("Hoparlörden çalınıyor...", "#00FF00")
                    time.sleep(duration)
                    arduino.close()
                    
                    self.set_status(f"Tamamlandı! Kayıt: {output_filepath}", "#00FF00")
                except Exception as e:
                    self.set_status("HATA: Bağlantı kurulamadı!", "#FF0000")
                    messagebox.showerror("Port Hatası", f"Cihaz meşgul veya seçilen porta erişilemedi:\n{e}\n\nLütfen Serial Monitor'ü kapatıp tekrar deneyin.")
            else:
                self.set_status(f"Sadece PC'ye Kaydedildi: {output_filepath}", "#00FF00")
                
        except Exception as ex:
            self.set_status("Sentez hatası!", "#FF0000")
            messagebox.showerror("Hata", f"Beklenmeyen bir hata oluştu:\n{ex}")
            
        finally:
            # Re-enable the button in the main thread
            self.root.after(0, lambda: self.play_btn.state(["!disabled"]))

if __name__ == "__main__":
    root = tk.Tk()
    app = TTSApp(root)
    root.mainloop()
