import random
import tkinter as tk
from tkinter import messagebox

# ------------------ Card and Deck Classes ------------------ #
class Card:
    suits = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
    ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'Jack', 'Queen', 'King', 'Ace']
    values = {rank: i + 2 for i, rank in enumerate(ranks)}

    def __init__(self, rank, suit):
        self.rank = rank
        self.suit = suit
        self.value = Card.values[rank]

    def __str__(self):
        return f"{self.rank} of {self.suit}"

class Deck:
    def __init__(self):
        self.cards = [Card(rank, suit) for suit in Card.suits for rank in Card.ranks]

    def shuffle(self):
        random.shuffle(self.cards)

    def draw_card(self):
        return self.cards.pop() if self.cards else None

# ------------------ Player Class ------------------ #
class Player:
    def __init__(self, name):
        self.name = name
        self.hand = []

    def draw_cards(self, deck, num=5):
        self.hand = []
        for _ in range(num):
            card = deck.draw_card()
            if card:
                self.hand.append(card)

    def show_hand(self):
        return [str(card) for card in self.hand]

    def highest_card(self):
        return max(self.hand, key=lambda c: c.value) if self.hand else None

# ------------------ GUI Game Class ------------------ #
class CardGameGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Playing with Cards - GUI Version")

        # Create deck and players
        self.deck = Deck()
        self.deck.shuffle()
        self.player1 = Player("Computer 1")
        self.player2 = Player("Computer 2")

        # Title label
        tk.Label(root, text="🎴 Card Game: Computer 1 vs Computer 2", font=("Arial", 16, "bold")).pack(pady=10)

        # Frames for cards
        self.frame1 = tk.LabelFrame(root, text="Computer 1's Cards", font=("Arial", 12))
        self.frame1.pack(padx=10, pady=5, fill="x")

        self.frame2 = tk.LabelFrame(root, text="Computer 2's Cards", font=("Arial", 12))
        self.frame2.pack(padx=10, pady=5, fill="x")

        # Play button
        self.play_btn = tk.Button(root, text="Play Game", font=("Arial", 12), bg="green", fg="white", command=self.play_game)
        self.play_btn.pack(pady=10)

        # Result label
        self.result_label = tk.Label(root, text="", font=("Arial", 14, "bold"), fg="blue")
        self.result_label.pack(pady=10)

    def play_game(self):
        # Reset deck and shuffle
        self.deck = Deck()
        self.deck.shuffle()

        # Draw cards
        self.player1.draw_cards(self.deck)
        self.player2.draw_cards(self.deck)

        # Display cards
        self.display_cards(self.frame1, self.player1.show_hand())
        self.display_cards(self.frame2, self.player2.show_hand())

        # Compare highest cards
        card1 = self.player1.highest_card()
        card2 = self.player2.highest_card()

        if card1.value > card2.value:
            winner_text = f"🏆 Winner: {self.player1.name} with {card1}"
        elif card1.value < card2.value:
            winner_text = f"🏆 Winner: {self.player2.name} with {card2}"
        else:
            winner_text = f"🤝 It's a tie! Both had {card1}"

        self.result_label.config(text=winner_text)

    def display_cards(self, frame, cards):
        # Clear old widgets
        for widget in frame.winfo_children():
            widget.destroy()

        # Display cards
        for card in cards:
            lbl = tk.Label(frame, text=card, font=("Arial", 11), relief="groove", width=18, padx=5, pady=3)
            lbl.pack(side="left", padx=5, pady=5)

# ------------------ Run the GUI ------------------ #
if __name__ == "__main__":
    root = tk.Tk()
    app = CardGameGUI(root)
    root.mainloop()

