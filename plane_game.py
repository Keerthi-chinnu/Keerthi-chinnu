import pygame
import random
import sys

# Initialize Pygame
pygame.init()
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Plane Obstacle Game")

# Colors
WHITE = (255, 255, 255)
SKY_TOP = (135, 206, 235)
SKY_BOTTOM = (0, 170, 255)
RED = (255, 0, 0)
GRAY = (200, 200, 200)
BLACK = (0, 0, 0)

clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 36)

# Plane setup
plane_width, plane_height = 70, 20
plane_x, plane_y = WIDTH * 0.1, HEIGHT // 2
plane_speed = 5

# Game state
obstacles = []
score = 0
game_speed = 3
slow_mode = False
slow_timer = 0
menu = True

# Difficulty settings
difficulty_levels = {
    'easy': (2, 2500, ['spike']),
    'normal': (3, 2000, ['spike', 'cloud']),
    'hard': (4, 1500, ['spike', 'cloud', 'bird']),
    'extreme': (6, 1000, ['spike', 'cloud', 'bird'])
}
difficulty = 'normal'
last_obstacle_time = pygame.time.get_ticks()

# Obstacle types
def draw_spike(x, y):
    pygame.draw.polygon(screen, RED, [(x+10, y), (x, y+40), (x+20, y+40)])

def draw_cloud(x, y):
    pygame.draw.ellipse(screen, GRAY, (x, y, 60, 30))
    pygame.draw.ellipse(screen, GRAY, (x+15, y-5, 60, 30))
    pygame.draw.ellipse(screen, GRAY, (x+30, y, 60, 30))

def draw_bird(x, y):
    pygame.draw.arc(screen, BLACK, (x, y, 20, 10), 0, 3.14, 2)
    pygame.draw.arc(screen, BLACK, (x+20, y, 20, 10), 0, 3.14, 2)

def draw_lightning(x, y):
    pygame.draw.polygon(screen, (255, 255, 0), [(x, y), (x+10, y+20), (x-5, y+20), (x+5, y+40)])

def draw_missile(x, y):
    pygame.draw.rect(screen, (50, 50, 50), (x, y, 40, 10))  # body
    pygame.draw.polygon(screen, RED, [(x+40, y), (x+50, y+5), (x+40, y+10)])  # tip


# Button class
class Button:
    def __init__(self, x, y, w, h, text, action=None):
        self.rect = pygame.Rect(x, y, w, h)
        self.color = GRAY
        self.text = text
        self.action = action

    def draw(self):
        pygame.draw.rect(screen, self.color, self.rect, border_radius=10)
        pygame.draw.rect(screen, BLACK, self.rect, 2, border_radius=10)
        text_surf = font.render(self.text, True, BLACK)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)

    def is_clicked(self, pos):
        return self.rect.collidepoint(pos)
    


# Buttons
start_button = Button(WIDTH // 2 - 100, 200, 200, 50, "Start Game", action='start')
diff_buttons = [
    Button(WIDTH // 2 - 180, 300, 90, 40, "Easy", action='easy'),
    Button(WIDTH // 2 - 90, 300, 90, 40, "Normal", action='normal'),
    Button(WIDTH // 2, 300, 90, 40, "Hard", action='hard'),
    Button(WIDTH // 2 + 90, 300, 90, 40, "Extreme", action='extreme'),
]

# Main loop
running = True
while running:
    screen.fill(SKY_BOTTOM)
    pygame.draw.rect(screen, SKY_TOP, (0, 0, WIDTH, HEIGHT // 2))

    if menu:
        # Draw menu
        title = font.render("Plane Obstacle Game", True, BLACK)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 100))

        start_button.draw()
        for btn in diff_buttons:
            btn.draw()

        selected_text = font.render(f"Selected: {difficulty.capitalize()}", True, BLACK)
        screen.blit(selected_text, (WIDTH // 2 - 100, 400))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                pos = pygame.mouse.get_pos()
                if start_button.is_clicked(pos):
                    menu = False
                    last_obstacle_time = pygame.time.get_ticks()
                    plane_x, plane_y = WIDTH * 0.1, HEIGHT // 2
                    score = 0
                    game_speed = difficulty_levels[difficulty][0]
                    obstacles.clear()
                    slow_mode = False
                for btn in diff_buttons:
                    if btn.is_clicked(pos):
                        difficulty = btn.action

        pygame.display.update()
        clock.tick(60)
        continue

    # --- Game is running ---

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    keys = pygame.key.get_pressed()
    if keys[pygame.K_UP]:
        plane_y = max(0, plane_y - plane_speed)
    if keys[pygame.K_DOWN]:
        plane_y = min(HEIGHT - plane_height, plane_y + plane_speed)
    if keys[pygame.K_LEFT]:
        plane_x = max(0, plane_x - plane_speed)
    if keys[pygame.K_RIGHT]:
        plane_x = min(WIDTH - plane_width, plane_x + plane_speed)
    if keys[pygame.K_SPACE] and not slow_mode:
        slow_mode = True
        slow_timer = pygame.time.get_ticks()
        game_speed /= 2

    if slow_mode and pygame.time.get_ticks() - slow_timer > 5000:
        game_speed *= 2
        slow_mode = False

    # Draw plane
    pygame.draw.rect(screen, WHITE, (plane_x, plane_y, plane_width, plane_height))
    pygame.draw.rect(screen, WHITE, (plane_x+20, plane_y-10, 50, 12))  # wing
    pygame.draw.rect(screen, WHITE, (plane_x-10, plane_y-10, 20, 10))  # tail

    # Score
    score += 0.1
    score_text = font.render(f"Score: {int(score)}", True, BLACK)
    screen.blit(score_text, (WIDTH - 150, 20))

    if slow_mode:
        slow_text = font.render("SLOW MODE", True, RED)
        screen.blit(slow_text, (20, 20))

    # Spawn obstacles
    now = pygame.time.get_ticks()
    if now - last_obstacle_time > difficulty_levels[difficulty][1]:
        obstacle_type = random.choice(difficulty_levels[difficulty][2])
        y = random.randint(50, HEIGHT - 60)
        obstacles.append({'type': obstacle_type, 'x': WIDTH, 'y': y})
        last_obstacle_time = now

    # Move and draw obstacles
    plane_rect = pygame.Rect(plane_x, plane_y, plane_width, plane_height)
    for obs in list(obstacles):
        obs['x'] -= game_speed
        if obs['type'] == 'spike':
            draw_spike(obs['x'], obs['y'])
            obs_rect = pygame.Rect(obs['x'], obs['y'], 20, 40)
        elif obs['type'] == 'cloud':
            draw_cloud(obs['x'], obs['y'])
            obs_rect = pygame.Rect(obs['x'], obs['y'], 90, 40)
        elif obs['type'] == 'bird':
            draw_bird(obs['x'], obs['y'])
            obs_rect = pygame.Rect(obs['x'], obs['y'], 40, 20)
        elif obs['type'] == 'lightning':
            draw_lightning(obs['x'], obs['y'])
            obs_rect = pygame.Rect(obs['x'], obs['y'], 20, 40)
        elif obs['type'] == 'missile':
            draw_missile(obs['x'], obs['y'])
            obs_rect = pygame.Rect(obs['x'], obs['y'], 50, 10)
    

        if plane_rect.colliderect(obs_rect):
            print("Game Over")
            menu = True  # Return to menu
            pygame.time.wait(1000)

        if obs['x'] < -100:
            obstacles.remove(obs)


    pygame.display.update()
    clock.tick(60)

pygame.quit()
sys.exit()
