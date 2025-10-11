import tkinter as tk
from tkinter import messagebox

# Main Game Class
class TicTacToe:
    def __init__(self, root):
        self.root = root
        self.root.title("Touch Interactive Tic Tac Toe")
        self.player = "X"
        self.buttons = [[None for _ in range(3)] for _ in range(3)]
        self.create_buttons()

    # Create the 3x3 grid of buttons
    def create_buttons(self):
        for row in range(3):
            for col in range(3):
                button = tk.Button(self.root, text=" ", font=('Helvetica', 40), height=2, width=5,
                                   command=lambda r=row, c=col: self.on_click(r, c))
                button.grid(row=row, column=col)
                self.buttons[row][col] = button

    # Handle button clicks (touch/mouse)
    def on_click(self, row, col):
        button = self.buttons[row][col]
        if button["text"] == " ":
            button["text"] = self.player
            if self.check_winner():
                messagebox.showinfo("Game Over", f"Player {self.player} wins!")
                self.reset_board()
            elif self.check_draw():
                messagebox.showinfo("Game Over", "It's a Draw!")
                self.reset_board()
            else:
                self.player = "O" if self.player == "X" else "X"

    # Check for a winner
    def check_winner(self):
        for row in range(3):
            if self.buttons[row][0]["text"] == self.buttons[row][1]["text"] == self.buttons[row][2]["text"] != " ":
                return True
        for col in range(3):
            if self.buttons[0][col]["text"] == self.buttons[1][col]["text"] == self.buttons[2][col]["text"] != " ":
                return True
        if self.buttons[0][0]["text"] == self.buttons[1][1]["text"] == self.buttons[2][2]["text"] != " ":
            return True
        if self.buttons[0][2]["text"] == self.buttons[1][1]["text"] == self.buttons[2][0]["text"] != " ":
            return True
        return False

    # Check for a draw
    def check_draw(self):
        for row in range(3):
            for col in range(3):
                if self.buttons[row][col]["text"] == " ":
                    return False
        return True

    # Reset the board for a new game
    def reset_board(self):
        for row in range(3):
            for col in range(3):
                self.buttons[row][col]["text"] = " "
        self.player = "X"

# Run the Game
if __name__ == "__main__":
    root = tk.Tk()
    game = TicTacToe(root)
    root.mainloop()
