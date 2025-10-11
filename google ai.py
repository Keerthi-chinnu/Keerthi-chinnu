import google.generativeai as genai
import customtkinter as ctk
from tkinter import scrolledtext

# ===========================
# ⚡️ Configure Gemini API
# ===========================
API_KEY = 'AIzaSyCn0RUK5ZQjUJoUzvl8GbgmarTSOGU0-oI'
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")
chat = model.start_chat()

# ===========================
# 🎨 Build the GUI
# ===========================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
root = ctk.CTk()
root.title("💬 Gemini Chat")
root.geometry("600x500")

chat_box = scrolledtext.ScrolledText(root, wrap="word")
chat_box.pack(pady=10, padx=10, fill="both", expand=True)
chat_box.configure(state='disabled')

# Entry and Send Button Frame
entry_frame = ctk.CTkFrame(root)
entry_frame.pack(pady=5, padx=10, fill="x")

entry = ctk.CTkEntry(entry_frame, placeholder_text="Type your message here...")
entry.pack(side="left", fill="x", expand=True, padx=(0,5))

def send_message():
    user_message = entry.get()
    if not user_message:
        return
    chat_box.configure(state='normal')
    chat_box.insert("end", "You: " + user_message + "\n")
    entry.delete(0, "end")
    try:
        response = chat.send_message(user_message)
        chat_box.insert("end", "Gemini: " + response.text + "\n")
    except Exception as e:
        chat_box.insert("end", "Error: " + str(e) + "\n")
    chat_box.configure(state='disabled')
    chat_box.yview("end")

send_button = ctk.CTkButton(entry_frame, text="▶️", width=40, command=send_message)
send_button.pack(side="right")
exit_button = ctk.CTkButton(root, text="Exit", command=root.destroy, fg_color="red")
exit_button.pack(pady=5)

root.mainloop()
