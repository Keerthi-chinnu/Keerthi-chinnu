import tkinter as tk
import random

# Dice face representations using Unicode characters
DICE_UNICODE = {
    1: "\u2680",  # ⚀
    2: "\u2681",  # ⚁
    3: "\u2682",  # ⚂
    4: "\u2683",  # ⚃
    5: "\u2684",  # ⚄
    6: "\u2685",  # ⚅
}

# Function to roll the dice
def roll_dice():
    dice_number = random.randint(1, 6)
    dice_label.config(text=DICE_UNICODE[dice_number], font=("Helvetica", 100))
    result_label.config(text=f"You rolled: {dice_number}", font=("Helvetica", 18))

# GUI window setup
root = tk.Tk()
root.title("🎲 Touch Dice Simulator")
root.geometry("300x300")
root.configure(bg="white")

# Dice display label
dice_label = tk.Label(root, text="🎲", font=("Helvetica", 100), bg="white")
dice_label.pack(pady=20)

# Result label
result_label = tk.Label(root, text="", font=("Helvetica", 16), bg="white")
result_label.pack()

# Roll button (works for touch screens)
roll_button = tk.Button(
    root, text="Tap to Roll", font=("Helvetica", 20),
    bg="#4CAF50", fg="white", padx=20, pady=10, command=roll_dice
)
roll_button.pack(pady=20)

# Start the GUI event loop
root.mainloop()
