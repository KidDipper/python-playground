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

            # 移動コストは「隣接セルの静的コスト」を利用
            tentative_gscore = gscore[current] + grid[neighbor[0]][neighbor[1]]
            if neighbor in closed_set and tentative_gscore >= gscore.get(neighbor, float('inf')):
                continue

            if tentative_gscore < gscore.get(neighbor, float('inf')):
                came_from[neighbor] = current
                gscore[neighbor] = tentative_gscore
                # ヒューリスティックは最低コスト1を前提に計算
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
    グリッド、各セルの状態、経路、そして各種コスト（セルの静的コストおよびg値）を描画する。
    ・障害物: 黒で塗りつぶし
    ・自由セル: 枠線
    ・オープンリスト: シアン
    ・クローズドリスト: オレンジ
    ・現在処理中ノード: マゼンタ
    ・最終経路: 緑
    ・スタート/ゴール: 濃い緑／濃い赤
    ・セル左上に静的コスト、中央にg値（存在すれば）を表示
    """
    screen.fill((255, 255, 255))
    rows = len(grid)
    cols = len(grid[0])
    
    # セル用フォント
    static_font = pygame.font.SysFont(None, 16)  # 各セルの静的コスト用
    g_font = pygame.font.SysFont(None, 18)       # g値用
    
    # グリッドと障害物・セル本体の描画
    for i in range(rows):
        for j in range(cols):
            rect = pygame.Rect(j * cell_size, i * cell_size, cell_size, cell_size)
            if grid[i][j] == -1:
                pygame.draw.rect(screen, (0, 0, 0), rect)  # 障害物は黒
            else:
                pygame.draw.rect(screen, (255, 255, 255), rect)
                # セルの静的コストを左上に表示（薄いグレー）
                cost_text = static_font.render(str(grid[i][j]), True, (100, 100, 100))
                screen.blit(cost_text, (j * cell_size + 2, i * cell_size + 2))
            pygame.draw.rect(screen, (200, 200, 200), rect, 1)
    
    # クローズドリスト（評価済みノード）をオレンジで
    for cell in closed_set:
        i, j = cell
        rect = pygame.Rect(j * cell_size, i * cell_size, cell_size, cell_size)
        pygame.draw.rect(screen, (255, 165, 0), rect)
    
    # オープンリスト（未評価の候補）をシアンで
    for item in open_heap:
        cell = item[1]
        i, j = cell
        rect = pygame.Rect(j * cell_size, i * cell_size, cell_size, cell_size)
        pygame.draw.rect(screen, (0, 255, 255), rect)
    
    # 現在評価中のノードをマゼンタで
    i, j = current
    rect = pygame.Rect(j * cell_size, i * cell_size, cell_size, cell_size)
    pygame.draw.rect(screen, (255, 0, 255), rect)
    
    # 経路が確定している場合は緑で描画
    if path:
        for cell in path:
            i, j = cell
            rect = pygame.Rect(j * cell_size, i * cell_size, cell_size, cell_size)
            pygame.draw.rect(screen, (0, 255, 0), rect)
    
    # スタートとゴールの描画（スタート：濃い緑、ゴール：濃い赤）
    i, j = start
    rect = pygame.Rect(j * cell_size, i * cell_size, cell_size, cell_size)
    pygame.draw.rect(screen, (0, 200, 0), rect)
    
    i, j = goal
    rect = pygame.Rect(j * cell_size, i * cell_size, cell_size, cell_size)
    pygame.draw.rect(screen, (200, 0, 0), rect)
    
    # 各セルの探索開始からの累積コスト（gscore）を中央に表示
    for i in range(rows):
        for j in range(cols):
            cell = (i, j)
            if cell in gscore:
                cost_val = gscore[cell]
                g_text = g_font.render(str(cost_val), True, (0, 0, 0))
                text_rect = g_text.get_rect(center=(j * cell_size + cell_size // 2, i * cell_size + cell_size // 2))
                screen.blit(g_text, text_rect)

def draw_button(screen, button_rect, text_str):
    """ボタンの描画（背景、枠、テキスト）"""
    pygame.draw.rect(screen, (150, 150, 150), button_rect)
    font = pygame.font.SysFont(None, 24)
    text = font.render(text_str, True, (0, 0, 0))
    text_rect = text.get_rect(center=button_rect.center)
    screen.blit(text, text_rect)

def main():
    pygame.init()
    cell_size = 40
    rows, cols = 7, 7
    button_height = 50  # 下部のボタン領域の高さ
    grid_height = rows * cell_size
    screen_width = cols * cell_size
    screen_height = grid_height + button_height
    
    screen = pygame.display.set_mode((screen_width, screen_height))
    pygame.display.set_caption("A* 経路探索 可視化 (セル毎のコスト付き・再生成ボタン付き)")
    
    # 初回グリッド生成：障害物とランダムな移動コスト付き
    grid = generate_grid(rows, cols, obstacle_probability=0.3, cost_min=1, cost_max=5)
    start = (0, 0)
    goal = (rows - 1, cols - 1)
    
    generator = astar_visualize(grid, start, goal)
    clock = pygame.time.Clock()
    path = []
    finished = False
    
    # 下部スペースに「再生成」ボタンを配置
    button_rect = pygame.Rect(10, grid_height + 10, 100, 30)
    
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                # 再生成ボタンがクリックされた場合
                if button_rect.collidepoint(event.pos):
                    grid = generate_grid(rows, cols, obstacle_probability=0.3, cost_min=1, cost_max=5)
                    generator = astar_visualize(grid, start, goal)
                    finished = False
                    path = []
        
        if not finished:
            try:
                open_heap, closed_set, came_from, current, finished_flag, gscore, fscore = next(generator)
                if finished_flag:
                    path = reconstruct_path(came_from, goal)
                    finished = True
            except StopIteration:
                finished = True
        
        # グリッド、各種状態、コスト値を描画
        draw_grid(screen, grid, cell_size, open_heap, closed_set, came_from, current, start, goal, path, gscore)
        # 画面下部に「再生成」ボタンを描画
        draw_button(screen, button_rect, "Retry")
        
        pygame.display.update()
        clock.tick(5)

if __name__ == "__main__":
    main()
