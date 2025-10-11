import tkinter as tk
import math

# Create main window
root = tk.Tk()
root.title("Professional Calculator")
root.geometry("400x600")

# Entry field
entry = tk.Entry(root, font=("Arial", 20), borderwidth=5, relief="sunken", justify='right')
entry.pack(pady=20, padx=10, fill='x')

# Function Definitions
def insert_value(value):
    entry.insert(tk.END, value)

def clear():
    entry.delete(0, tk.END)

def calculate():
    try:
        result = eval(entry.get())
        entry.delete(0, tk.END)
        entry.insert(0, result)
    except:
        entry.delete(0, tk.END)
        entry.insert(0, "Error")

def sqrt():
    try:
        value = float(entry.get())
        entry.delete(0, tk.END)
        entry.insert(0, math.sqrt(value))
    except:
        entry.insert(0, "Error")

def log():
    try:
        value = float(entry.get())
        entry.delete(0, tk.END)
        entry.insert(0, math.log10(value))
    except:
        entry.insert(0, "Error")

def sin():
    try:
        value = math.radians(float(entry.get()))
        entry.delete(0, tk.END)
        entry.insert(0, math.sin(value))
    except:
        entry.insert(0, "Error")

def cos():
    try:
        value = math.radians(float(entry.get()))
        entry.delete(0, tk.END)
        entry.insert(0, math.cos(value))
    except:
        entry.insert(0, "Error")

def tan():
    try:
        value = math.radians(float(entry.get()))
        entry.delete(0, tk.END)
        entry.insert(0, math.tan(value))
    except:
        entry.insert(0, "Error")

# Button Layout
buttons = [
    ('7', '8', '9', '/'),
    ('4', '5', '6', '*'),
    ('1', '2', '3', '-'),
    ('0', '.', '=', '+'),
]

# Create button widgets for numbers and operators
for row in buttons:
    frame = tk.Frame(root)
    frame.pack(pady=5)
    for btn in row:
        if btn == '=':
            tk.Button(frame, text=btn, font=("Arial", 18), command=calculate, width=5, height=2).pack(side='left', padx=5)
        else:
            tk.Button(frame, text=btn, font=("Arial", 18), command=lambda b=btn: insert_value(b), width=5, height=2).pack(side='left', padx=5)

# Scientific function buttons
sci_buttons = [
    ('sqrt', sqrt),
    ('log', log),
    ('sin', sin),
    ('cos', cos),
    ('tan', tan),
]

frame = tk.Frame(root)
frame.pack(pady=10)
for (label, func) in sci_buttons:
    tk.Button(frame, text=label, font=("Arial", 14), command=func, width=6, height=2).pack(side='left', padx=5)

# Clear button
tk.Button(root, text="Clear", font=("Arial", 14), command=clear, bg="red", fg="white", width=20).pack(pady=10)

# Run the application
root.mainloop()
