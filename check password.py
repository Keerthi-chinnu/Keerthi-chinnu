import time
import random

password = input("Enter password to check: ")

keys = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()/,."

guess = ""
attempts = 0
start_time = time.time()

for real_char in password:
    found = False
    while not found:
        attempts += 1
        char = random.choice(keys)
        print("Trying:", guess + char)

        if char == real_char:
            guess += char
            found = True

end_time = time.time()

print("\nPassword cracked:", guess)
print("Total attempts:", attempts)
print("Time taken:", round(end_time - start_time, 2), "seconds")
