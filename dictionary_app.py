import tkinter as tk
from tkinter import ttk, scrolledtext
import json
import os

class DictionaryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Offline English Dictionary")
        self.root.geometry("800x600")
        self.root.configure(bg="#1e1e1e")
        
        # Load dictionary data
        self.dictionary = self.load_dictionary()
        
        # Configure font
        self.font_family = "IBM Plex Mono"
        self.font_size = 11
        
        # Create UI
        self.create_widgets()
        
    def load_dictionary(self):
        """Load dictionary from JSON file"""
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dict_file = os.path.join(script_dir, "dictionary_data.json")
        
        if os.path.exists(dict_file):
            with open(dict_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            print(f"Warning: {dict_file} not found. Creating sample dictionary...")
            # Return a sample dictionary if file doesn't exist
            return self.create_sample_dictionary()
    
    def create_sample_dictionary(self):
        """Create a basic sample dictionary"""
        return {
            "hello": {
                "part_of_speech": "interjection",
                "definition": "Used as a greeting or to begin a telephone conversation.",
                "example": "Hello, how are you today?"
            },
            "world": {
                "part_of_speech": "noun",
                "definition": "The earth, together with all of its countries, peoples, and natural features.",
                "example": "He traveled around the world."
            },
            "python": {
                "part_of_speech": "noun",
                "definition": "A large heavy-bodied nonvenomous snake occurring throughout the Old World tropics.",
                "example": "The python coiled around the branch."
            },
            "dictionary": {
                "part_of_speech": "noun",
                "definition": "A book or electronic resource that lists the words of a language and gives their meaning.",
                "example": "I looked up the word in the dictionary."
            },
            "search": {
                "part_of_speech": "verb",
                "definition": "Try to find something by looking or otherwise seeking carefully and thoroughly.",
                "example": "She searched for her missing keys."
            }
        }
    
    def create_widgets(self):
        """Create all GUI widgets"""
        # Title
        title_label = tk.Label(
            self.root,
            text="English Dictionary",
            font=(self.font_family, 20, "bold"),
            bg="#1e1e1e",
            fg="#ffffff"
        )
        title_label.pack(pady=20)
        
        # Search frame
        search_frame = tk.Frame(self.root, bg="#1e1e1e")
        search_frame.pack(pady=10, padx=20, fill="x")
        
        # Search label
        search_label = tk.Label(
            search_frame,
            text="Search Word:",
            font=(self.font_family, self.font_size),
            bg="#1e1e1e",
            fg="#ffffff"
        )
        search_label.pack(side="left", padx=(0, 10))
        
        # Search entry
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.on_search_change)
        
        self.search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            font=(self.font_family, self.font_size),
            bg="#2d2d2d",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief="flat",
            width=40
        )
        self.search_entry.pack(side="left", fill="x", expand=True, ipady=5)
        self.search_entry.focus()
        
        # Search button
        self.search_button = tk.Button(
            search_frame,
            text="Search",
            command=self.search_word,
            font=(self.font_family, self.font_size),
            bg="#0066cc",
            fg="#ffffff",
            relief="flat",
            cursor="hand2",
            padx=20
        )
        self.search_button.pack(side="left", padx=(10, 0), ipady=5)
        
        # Suggestions frame
        self.suggestions_frame = tk.Frame(self.root, bg="#1e1e1e")
        self.suggestions_frame.pack(pady=5, padx=20, fill="x")
        
        # Suggestions listbox
        self.suggestions_listbox = tk.Listbox(
            self.suggestions_frame,
            font=(self.font_family, 9),
            bg="#2d2d2d",
            fg="#ffffff",
            selectbackground="#0066cc",
            relief="flat",
            height=5
        )
        self.suggestions_listbox.pack_forget()  # Hide initially
        self.suggestions_listbox.bind('<<ListboxSelect>>', self.on_suggestion_select)
        
        # Result frame
        result_frame = tk.Frame(self.root, bg="#1e1e1e")
        result_frame.pack(pady=10, padx=20, fill="both", expand=True)
        
        # Result text area with scrollbar
        self.result_text = scrolledtext.ScrolledText(
            result_frame,
            font=(self.font_family, self.font_size),
            bg="#2d2d2d",
            fg="#ffffff",
            relief="flat",
            wrap="word",
            padx=15,
            pady=15
        )
        self.result_text.pack(fill="both", expand=True)
        
        # Configure text tags for formatting
        self.result_text.tag_configure("word", font=(self.font_family, 18, "bold"), foreground="#4db8ff")
        self.result_text.tag_configure("pos", font=(self.font_family, 11, "italic"), foreground="#ffaa00")
        self.result_text.tag_configure("definition", font=(self.font_family, 11), foreground="#ffffff")
        self.result_text.tag_configure("example", font=(self.font_family, 10, "italic"), foreground="#88ff88")
        self.result_text.tag_configure("label", font=(self.font_family, 10, "bold"), foreground="#cccccc")
        
        # Bind Enter key to search
        self.search_entry.bind('<Return>', lambda e: self.search_word())
        
        # Display welcome message
        self.show_welcome_message()
    
    def show_welcome_message(self):
        """Display welcome message"""
        self.result_text.delete(1.0, tk.END)
        welcome = f"""Welcome to Offline English Dictionary!

Total words in database: {len(self.dictionary)}

Type a word in the search box above and press Enter or click Search.

Examples: hello, world, python, dictionary, search"""
        self.result_text.insert(1.0, welcome)
    
    def on_search_change(self, *args):
        """Handle search text changes for auto-suggestions"""
        search_term = self.search_var.get().lower().strip()
        
        if len(search_term) >= 2:
            # Find matching words
            matches = [word for word in self.dictionary.keys() 
                      if word.startswith(search_term)][:10]
            
            if matches:
                self.suggestions_listbox.delete(0, tk.END)
                for match in matches:
                    self.suggestions_listbox.insert(tk.END, match)
                self.suggestions_listbox.pack(fill="x")
            else:
                self.suggestions_listbox.pack_forget()
        else:
            self.suggestions_listbox.pack_forget()
    
    def on_suggestion_select(self, event):
        """Handle suggestion selection"""
        selection = self.suggestions_listbox.curselection()
        if selection:
            word = self.suggestions_listbox.get(selection[0])
            self.search_var.set(word)
            self.suggestions_listbox.pack_forget()
            self.search_word()
    
    def search_word(self):
        """Search for a word in the dictionary"""
        word = self.search_var.get().lower().strip()
        self.suggestions_listbox.pack_forget()
        
        if not word:
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(1.0, "Please enter a word to search.")
            return
        
        if word in self.dictionary:
            self.display_definition(word, self.dictionary[word])
        else:
            self.display_not_found(word)
    
    def display_definition(self, word, data):
        """Display word definition"""
        self.result_text.delete(1.0, tk.END)
        
        # Word
        self.result_text.insert(tk.END, f"{word.upper()}\n\n", "word")
        
        # Part of speech
        if "part_of_speech" in data:
            self.result_text.insert(tk.END, f"({data['part_of_speech']})\n\n", "pos")
        
        # Definition
        if "definition" in data:
            self.result_text.insert(tk.END, "Definition:\n", "label")
            self.result_text.insert(tk.END, f"{data['definition']}\n\n", "definition")
        
        # Example
        if "example" in data:
            self.result_text.insert(tk.END, "Example:\n", "label")
            self.result_text.insert(tk.END, f'"{data["example"]}"', "example")
    
    def display_not_found(self, word):
        """Display not found message"""
        self.result_text.delete(1.0, tk.END)
        
        message = f'Word "{word}" not found in the dictionary.\n\n'
        
        # Suggest similar words
        similar = self.find_similar_words(word)
        if similar:
            message += "Did you mean:\n"
            for similar_word in similar[:5]:
                message += f"  - {similar_word}\n"
        
        self.result_text.insert(1.0, message)
    
    def find_similar_words(self, word):
        """Find similar words using simple string matching"""
        similar = []
        for dict_word in self.dictionary.keys():
            if word in dict_word or dict_word in word:
                similar.append(dict_word)
        return sorted(similar)[:5]

def main():
    root = tk.Tk()
    app = DictionaryApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()