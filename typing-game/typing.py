import pygame
import random
import string
import time

# Pygameの初期化
pygame.init()

# 画面設定
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("タイピングゲーム")

# 色の定義
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)

# フォント設定
FONT_LARGE = pygame.font.Font(None, 74)
FONT_MEDIUM = pygame.font.Font(None, 48)
FONT_SMALL = pygame.font.Font(None, 36)

class TypingGame:
    def __init__(self):
        self.stage = 1
        self.max_stages = 10
        self.time_limit = 10
        self.input_text = ""
        self.target_text = ""
        self.game_state = "stage_intro"  # stage_intro, playing, clear, failed
        self.start_time = 0
        self.countdown = 3
        self.typing_speed = 0  # 入力速度（文字/分）
        self.last_input_time = 0  # 最後の入力時間
        
        # ボタンの設定を追加
        self.retry_button = pygame.Rect(SCREEN_WIDTH//2 - 100, SCREEN_HEIGHT//2 + 50, 200, 50)
        self.quit_button = pygame.Rect(SCREEN_WIDTH//2 - 100, SCREEN_HEIGHT//2 + 120, 200, 50)

        # タイマーバーの設定を追加
        self.timer_bar_width = 400
        self.timer_bar_height = 30
        self.timer_bar_x = SCREEN_WIDTH//2 - self.timer_bar_width//2
        self.timer_bar_y = 20
        self.pulse_scale = 1.0
        self.pulse_direction = 1

    def generate_target_text(self):
        # ステージに応じて文字数を増やす
        length = self.stage * 3
        return ''.join(random.choices(string.ascii_lowercase, k=length))

    def draw_stage_intro(self):
        screen.fill(WHITE)
        stage_text = FONT_LARGE.render(f"STAGE {self.stage}", True, BLACK)
        countdown_text = FONT_LARGE.render(str(int(self.countdown)), True, BLACK)
        speed_text = FONT_SMALL.render(f"Previous Speed: {self.typing_speed:.1f} chars/min", True, BLACK)
        
        screen.blit(stage_text, (SCREEN_WIDTH//2 - stage_text.get_width()//2, SCREEN_HEIGHT//2 - 50))
        screen.blit(countdown_text, (SCREEN_WIDTH//2 - countdown_text.get_width()//2, SCREEN_HEIGHT//2 + 50))
        screen.blit(speed_text, (SCREEN_WIDTH//2 - speed_text.get_width()//2, SCREEN_HEIGHT//2 + 120))

    def draw_timer(self, remaining_time):
        # バーの背景
        pygame.draw.rect(screen, (200, 200, 200), 
                        (self.timer_bar_x, self.timer_bar_y, 
                         self.timer_bar_width, self.timer_bar_height))
        
        # 残り時間に応じたバーの長さを計算
        bar_length = (remaining_time / self.time_limit) * self.timer_bar_width
        
        # バーの色を設定（3秒以下で赤く）
        bar_color = RED if remaining_time <= 3 else (0, 150, 0)
        
        # タイマーバーを描画
        pygame.draw.rect(screen, bar_color,
                        (self.timer_bar_x, self.timer_bar_y, 
                         bar_length, self.timer_bar_height))
        
        # 残り時間のテキスト
        if remaining_time <= 3:
            # パルスエフェクトの更新
            self.pulse_scale += 0.1 * self.pulse_direction
            if self.pulse_scale >= 1.5:
                self.pulse_direction = -1
            elif self.pulse_scale <= 1.0:
                self.pulse_direction = 1
                
            # パルスエフェクトを適用したフォントサイズ
            pulse_font = pygame.font.Font(None, int(48 * self.pulse_scale))
            time_text = pulse_font.render(f"{remaining_time:.1f}", True, RED)
        else:
            time_text = FONT_MEDIUM.render(f"{remaining_time:.1f}", True, BLACK)
        
        # テキストをバーの右側に表示
        text_x = self.timer_bar_x + self.timer_bar_width + 20
        text_y = self.timer_bar_y + (self.timer_bar_height - time_text.get_height())//2
        screen.blit(time_text, (text_x, text_y))

    def draw_game_screen(self):
        screen.fill(WHITE)
        
        # ステージ表示
        stage_text = FONT_SMALL.render(f"Stage {self.stage}/{self.max_stages}", True, BLACK)
        screen.blit(stage_text, (20, 20))
        
        # タイマー表示を更新
        remaining_time = max(0, self.time_limit - (time.time() - self.start_time))
        self.draw_timer(remaining_time)

        # ターゲットテキスト表示
        target_surface = FONT_MEDIUM.render(self.target_text, True, BLACK)
        screen.blit(target_surface, (SCREEN_WIDTH//2 - target_surface.get_width()//2, SCREEN_HEIGHT//2 - 50))

        # 入力テキスト表示
        input_surface = FONT_MEDIUM.render(self.input_text, True, BLACK)
        screen.blit(input_surface, (SCREEN_WIDTH//2 - input_surface.get_width()//2, SCREEN_HEIGHT//2 + 50))

        # 入力指示の表示
        instruction_text = FONT_SMALL.render("Press Enter when finished", True, BLACK)
        screen.blit(instruction_text, (SCREEN_WIDTH//2 - instruction_text.get_width()//2, SCREEN_HEIGHT//2 + 100))

    def draw_clear_screen(self):
        screen.fill(WHITE)
        clear_text = FONT_LARGE.render("GAME CLEAR!", True, BLACK)
        screen.blit(clear_text, (SCREEN_WIDTH//2 - clear_text.get_width()//2, SCREEN_HEIGHT//2))

    def draw_failed_screen(self):
        screen.fill(WHITE)
        # 失敗メッセージ
        failed_text = FONT_LARGE.render("TIME OVER!", True, RED)
        screen.blit(failed_text, (SCREEN_WIDTH//2 - failed_text.get_width()//2, SCREEN_HEIGHT//2 - 50))
        
        # Retryボタン
        pygame.draw.rect(screen, BLACK, self.retry_button)
        retry_text = FONT_MEDIUM.render("Retry", True, WHITE)
        screen.blit(retry_text, (self.retry_button.centerx - retry_text.get_width()//2, 
                                self.retry_button.centery - retry_text.get_height()//2))
        
        # Quitボタン
        pygame.draw.rect(screen, BLACK, self.quit_button)
        quit_text = FONT_MEDIUM.render("Quit", True, WHITE)
        screen.blit(quit_text, (self.quit_button.centerx - quit_text.get_width()//2, 
                               self.quit_button.centery - quit_text.get_height()//2))

    def run(self):
        clock = pygame.time.Clock()
        running = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                if event.type == pygame.MOUSEBUTTONDOWN and self.game_state == "failed":
                    mouse_pos = event.pos
                    if self.retry_button.collidepoint(mouse_pos):
                        # リトライ処理
                        self.game_state = "stage_intro"
                        self.countdown = 3
                        self.input_text = ""
                    elif self.quit_button.collidepoint(mouse_pos):
                        running = False

                if event.type == pygame.KEYDOWN and self.game_state == "playing":
                    if event.key == pygame.K_RETURN:
                        # 入力速度の計算
                        elapsed_time = time.time() - self.last_input_time
                        if elapsed_time > 0:
                            self.typing_speed = (len(self.input_text) / elapsed_time) * 60
                        
                        if self.input_text == self.target_text:
                            if self.stage == self.max_stages:
                                self.game_state = "clear"
                            else:
                                self.stage += 1
                                self.game_state = "stage_intro"
                                self.countdown = 3
                        else:
                            # 入力が間違っている場合、入力バーをクリア
                            self.input_text = ""
                            self.last_input_time = time.time()
                    elif event.key == pygame.K_BACKSPACE:
                        self.input_text = self.input_text[:-1]
                    else:
                        if len(event.unicode.encode()) == 1:
                            if self.input_text == "":  # 最初の文字入力時
                                self.last_input_time = time.time()
                            self.input_text += event.unicode

            if self.game_state == "stage_intro":
                self.draw_stage_intro()
                self.countdown -= clock.get_time() / 1000
                if self.countdown <= 0:
                    self.game_state = "playing"
                    self.target_text = self.generate_target_text()
                    self.input_text = ""
                    self.start_time = time.time()
                    self.last_input_time = time.time()

            elif self.game_state == "playing":
                self.draw_game_screen()
                if time.time() - self.start_time >= self.time_limit:
                    self.game_state = "failed"  # 失敗画面に遷移

            elif self.game_state == "clear":
                self.draw_clear_screen()
                
            elif self.game_state == "failed":
                self.draw_failed_screen()

            pygame.display.flip()
            clock.tick(60)

        pygame.quit()

if __name__ == "__main__":
    game = TypingGame()
    game.run()
