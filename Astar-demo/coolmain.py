import pygame
import random
import heapq
import sys

def heuristic(a, b):
    """マンハッタン距離をヒューリスティックとして利用（最低移動コストが1の場合）"""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def astar_visualize(grid, start, goal):
    """
    A* アルゴリズム本体（ジェネレーター版）
    各イテレーションで以下の状態を yield します:
      - open_heap: 探索候補の優先キュー
      - closed_set: 評価済みノードのセット
      - came_from: 経路再構築用の親ノード辞書
      - current: 現在評価中のノード
      - finished_flag: ゴール到達か否かのフラグ
      - gscore: 開始から各ノードまでの累積コスト辞書
      - fscore: 推定総コスト辞書
    """
    open_heap = []
    heapq.heappush(open_heap, (heuristic(start, goal), start))
    closed_set = set()
    came_from = {}
    gscore = {start: 0}
    fscore = {start: heuristic(start, goal)}
    # 4方向移動（上下左右）
    neighbors = [(0, 1), (0, -1), (1, 0), (-1, 0)]
    
    while open_heap:
        current = heapq.heappop(open_heap)[1]
        yield open_heap, closed_set, came_from, current, False, gscore, fscore

        if current == goal:
            yield open_heap, closed_set, came_from, current, True, gscore, fscore
            return

        closed_set.add(current)

        for dx, dy in neighbors:
            neighbor = (current[0] + dx, current[1] + dy)
            # グリッド範囲外ならスキップ
            if neighbor[0] < 0 or neighbor[0] >= len(grid) or neighbor[1] < 0 or neighbor[1] >= len(grid[0]):
                continue
            # 障害物（-1）の場合はスキップ
            if grid[neighbor[0]][neighbor[1]] == -1:
                continue

            tentative_gscore = gscore[current] + grid[neighbor[0]][neighbor[1]]
            if neighbor in closed_set and tentative_gscore >= gscore.get(neighbor, float('inf')):
                continue

            if tentative_gscore < gscore.get(neighbor, float('inf')):
                came_from[neighbor] = current
                gscore[neighbor] = tentative_gscore
                fscore[neighbor] = tentative_gscore + heuristic(neighbor, goal)
                heapq.heappush(open_heap, (fscore[neighbor], neighbor))
    
    yield open_heap, closed_set, came_from, current, False, gscore, fscore

def reconstruct_path(came_from, current):
    """ゴールから逆に辿って経路を再構築する"""
    path = []
    while current in came_from:
        path.append(current)
        current = came_from[current]
    path.append(current)
    path.reverse()
    return path

def generate_grid(rows, cols, obstacle_probability=0.3, cost_min=1, cost_max=5):
    """
    ランダムに障害物とセルの移動コストを設定したグリッドを生成する。
    - 各セルは、障害物なら -1、それ以外なら cost_min～cost_max のランダムな整数値を持つ
    - スタートおよびゴールは必ず通行可能に（コストは1に固定）
    """
    grid = []
    for i in range(rows):
        row = []
        for j in range(cols):
            if random.random() < obstacle_probability:
                row.append(-1)  # 障害物
            else:
                row.append(random.randint(cost_min, cost_max))
        grid.append(row)
    
    grid[0][0] = 1
    grid[rows - 1][cols - 1] = 1
    return grid

def draw_grid(screen, grid, cell_size, open_heap, closed_set, came_from, current, start, goal, path, gscore):
    """
    グリッド、各セルの状態、経路、各種コストを描画します。
    ・背景は暗色。セルは丸みのある四角形。
    ・障害物は「石」をイメージした円で描画します。
    ・評価済みノード、候補ノード、現在処理中ノード、経路、スタート／ゴールにはそれぞれ個別の色を適用。
    ・セル内には静的コストと、g値（あれば）を表示します。
    """
    # 背景を塗りつぶし
    screen.fill((20, 20, 30))
    rows = len(grid)
    cols = len(grid[0])
    
    static_font = pygame.font.SysFont("Calibri", 16, bold=True)
    g_font = pygame.font.SysFont("Calibri", 18, bold=True)
    
    for i in range(rows):
        for j in range(cols):
            rect = pygame.Rect(j * cell_size + 2, i * cell_size + 2, cell_size - 4, cell_size - 4)
            if grid[i][j] == -1:
                # 障害物を石の形（丸）で描画
                center = (j * cell_size + cell_size // 2, i * cell_size + cell_size // 2)
                radius = cell_size // 2 - 4
                pygame.draw.circle(screen, (90, 90, 90), center, radius)
            else:
                pygame.draw.rect(screen, (60, 60, 80), rect, border_radius=8)
                # セル内左上に静的コスト
                cost_text = static_font.render(str(grid[i][j]), True, (120, 120, 180))
                screen.blit(cost_text, (j * cell_size + 6, i * cell_size + 2))
            # 軽い枠線
            pygame.draw.rect(screen, (80, 80, 100), rect, 1, border_radius=8)
    
    # クローズドリストをオレンジで
    for cell in closed_set:
        i, j = cell
        rect = pygame.Rect(j * cell_size + 2, i * cell_size + 2, cell_size - 4, cell_size - 4)
        pygame.draw.rect(screen, (255, 140, 0), rect, border_radius=8)
    
    # オープンリストをシアンで
    for item in open_heap:
        cell = item[1]
        i, j = cell
        rect = pygame.Rect(j * cell_size + 2, i * cell_size + 2, cell_size - 4, cell_size - 4)
        pygame.draw.rect(screen, (0, 206, 209), rect, border_radius=8)
    
    # 現在処理中のノードにパルスエフェクト
    if current:
        i, j = current
        t = pygame.time.get_ticks() / 1000.0
        offset = 2 + int((abs(0.5 - (t % 1)) * 4))
        rect = pygame.Rect(j * cell_size + offset, i * cell_size + offset, cell_size - offset * 2, cell_size - offset * 2)
        pygame.draw.rect(screen, (255, 105, 180), rect, border_radius=8)
    
    # 経路（確定した最短経路）は明るい緑で描画
    if path:
        for cell in path:
            i, j = cell
            rect = pygame.Rect(j * cell_size + 2, i * cell_size + 2, cell_size - 4, cell_size - 4)
            pygame.draw.rect(screen, (50, 205, 50), rect, border_radius=8)
    
    # スタート（濃い緑）とゴール（濃い赤）の描画
    i, j = start
    rect = pygame.Rect(j * cell_size + 2, i * cell_size + 2, cell_size - 4, cell_size - 4)
    pygame.draw.rect(screen, (0, 128, 0), rect, border_radius=8)
    
    i, j = goal
    rect = pygame.Rect(j * cell_size + 2, i * cell_size + 2, cell_size - 4, cell_size - 4)
    pygame.draw.rect(screen, (139, 0, 0), rect, border_radius=8)
    
    # 各セルに累積コスト gscore を中央に描画
    for i in range(rows):
        for j in range(cols):
            cell = (i, j)
            if cell in gscore:
                cost_val = gscore[cell]
                g_text = g_font.render(str(cost_val), True, (220, 220, 220))
                text_rect = g_text.get_rect(center=(j * cell_size + cell_size // 2, i * cell_size + cell_size // 2))
                screen.blit(g_text, text_rect)

def draw_button(screen, button_rect, text_str):
    """スタイリッシュな Retry ボタンの描画"""
    pygame.draw.rect(screen, (70, 70, 120), button_rect, border_radius=8)
    pygame.draw.rect(screen, (150, 150, 200), button_rect, 2, border_radius=8)
    font = pygame.font.SysFont("Calibri", 24, bold=True)
    text = font.render(text_str, True, (230, 230, 250))
    text_rect = text.get_rect(center=button_rect.center)
    screen.blit(text, text_rect)

def interpolate_cell_position(start_cell, end_cell, t, cell_size):
    """
    ２つのセルの中心座標間を t (0～1) で線形補間して返す。
    """
    start_x = start_cell[1] * cell_size + cell_size / 2
    start_y = start_cell[0] * cell_size + cell_size / 2
    end_x   = end_cell[1] * cell_size + cell_size / 2
    end_y   = end_cell[0] * cell_size + cell_size / 2
    pos_x = start_x + (end_x - start_x) * t
    pos_y = start_y + (end_y - start_y) * t
    return (int(pos_x), int(pos_y))

def draw_car(screen, pos, cell_size):
    """
    シンプルな車を pos（セル中心）に描画。
    ここでは赤い矩形を車として表現していますが、画像を利用することも可能です。
    """
    car_width = cell_size // 2
    car_height = cell_size // 2
    car_rect = pygame.Rect(0, 0, car_width, car_height)
    car_rect.center = pos
    pygame.draw.rect(screen, (255, 0, 0), car_rect, border_radius=5)

def main():
    pygame.init()
    cell_size = 40
    rows, cols = 7, 7
    button_height = 50  # 下部ボタン領域
    grid_height = rows * cell_size
    screen_width = cols * cell_size
    screen_height = grid_height + button_height
    
    screen = pygame.display.set_mode((screen_width, screen_height))
    pygame.display.set_caption("A* 経路探索 可視化 (石と車付き)")
    
    # 初回グリッド生成（障害物とランダム移動コスト付き）
    grid = generate_grid(rows, cols, obstacle_probability=0.3, cost_min=1, cost_max=5)
    start = (0, 0)
    goal = (rows - 1, cols - 1)
    
    generator = astar_visualize(grid, start, goal)
    clock = pygame.time.Clock()
    path = []
    finished = False

    # 車のアニメーション用の変数（経路上を移動）
    car_index = 0    # 現在の経路インデックス
    car_timer = 0    # セル間の補間用カウンター
    movement_delay = 20  # 1セル分の移動に必要なフレーム数（速度調整）
    
    # 下部に「Retry」ボタンを配置
    button_rect = pygame.Rect(10, grid_height + 10, 100, 30)
    
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if button_rect.collidepoint(event.pos):
                    grid = generate_grid(rows, cols, obstacle_probability=0.3, cost_min=1, cost_max=5)
                    generator = astar_visualize(grid, start, goal)
                    finished = False
                    path = []
                    # 車の位置リセット
                    car_index = 0
                    car_timer = 0
        
        if not finished:
            try:
                open_heap, closed_set, came_from, current, finished_flag, gscore, fscore = next(generator)
                if finished_flag:
                    path = reconstruct_path(came_from, goal)
                    finished = True
            except StopIteration:
                finished = True

        # グリッド、各種状態、経路を描画
        draw_grid(screen, grid, cell_size, open_heap, closed_set, came_from, current, start, goal, path, gscore)
        
        # 経路が確定していれば車のアニメーションを行う
        if finished and path:
            if car_index < len(path) - 1:
                car_timer += 1
                if car_timer >= movement_delay:
                    car_timer = 0
                    car_index += 1
                
                # 現在のセルと次のセルの中心間で線形補間
                if car_index < len(path) - 1:
                    t = car_timer / movement_delay
                    car_pos = interpolate_cell_position(path[car_index], path[car_index + 1], t, cell_size)
                else:
                    car_pos = (path[-1][1] * cell_size + cell_size // 2, path[-1][0] * cell_size + cell_size // 2)
            else:
                # 経路の最後のセルに到達
                car_pos = (path[-1][1] * cell_size + cell_size // 2, path[-1][0] * cell_size + cell_size // 2)
            draw_car(screen, car_pos, cell_size)
        
        # 下部に Retry ボタンの描画
        draw_button(screen, button_rect, "Retry")
        
        pygame.display.update()
        # 経路探索中は低速（例：5fps）、アニメーション時は多少滑らかに
        clock.tick(30 if finished and path else 5)

if __name__ == "__main__":
    main()
