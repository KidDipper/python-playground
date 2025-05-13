import pygame
import random
import heapq
import sys

# A* のヒューリスティック（マンハッタン距離）
def heuristic(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

# A* 探索：ジェネレーターで各ステップの状態を返す
def astar_visualize(grid, start, goal):
    open_heap = []
    heapq.heappush(open_heap, (heuristic(start, goal), start))
    closed_set = set()
    came_from = {}
    gscore = {start: 0}
    fscore = {start: heuristic(start, goal)}
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
            if neighbor[0] < 0 or neighbor[0] >= len(grid) or neighbor[1] < 0 or neighbor[1] >= len(grid[0]):
                continue
            if grid[neighbor[0]][neighbor[1]] == -1:
                continue  # 障害物ならスキップ
            
            tentative = gscore[current] + grid[neighbor[0]][neighbor[1]]
            if neighbor in closed_set and tentative >= gscore.get(neighbor, float('inf')):
                continue
            if tentative < gscore.get(neighbor, float('inf')):
                came_from[neighbor] = current
                gscore[neighbor] = tentative
                fscore[neighbor] = tentative + heuristic(neighbor, goal)
                heapq.heappush(open_heap, (fscore[neighbor], neighbor))
    
    yield open_heap, closed_set, came_from, current, False, gscore, fscore

# 経路再構築
def reconstruct_path(came_from, current):
    path = []
    while current in came_from:
        path.append(current)
        current = came_from[current]
    path.append(current)
    path.reverse()
    return path

# グリッドを生成（障害物は -1、その他は移動コスト）
def generate_grid(rows, cols, obstacle_probability=0.3, cost_min=1, cost_max=5):
    grid = []
    for i in range(rows):
        row = []
        for j in range(cols):
            if random.random() < obstacle_probability:
                row.append(-1)
            else:
                row.append(random.randint(cost_min, cost_max))
        grid.append(row)
    # スタート／ゴールは必ず通行可
    grid[0][0] = 1
    grid[rows - 1][cols - 1] = 1
    return grid

# アイソメトリック座標変換
def cart_to_iso(x, y, tile_width, tile_height, cam_offset):
    # x, y: グリッド（セル）の座標。横方向に j, 縦方向に i とする
    iso_x = (x - y) * (tile_width // 2) + cam_offset[0]
    iso_y = (x + y) * (tile_height // 4) + cam_offset[1]
    return int(iso_x), int(iso_y)

# 地面タイル（菱形）の描画
def draw_tile(screen, iso_top, tile_width, tile_height, color, outline_color, shift=0):
    x, y = iso_top
    points = [
        (x, y + shift),
        (x + tile_width // 2, y + tile_height // 4 + shift),
        (x, y + tile_height // 2 + shift),
        (x - tile_width // 2, y + tile_height // 4 + shift)
    ]
    pygame.draw.polygon(screen, color, points)
    pygame.draw.polygon(screen, outline_color, points, 1)

# グリッド全体（背景や障害物、経路、開始／終了マーカーなど）の描画
def draw_grid(screen, grid, tile_width, tile_height, cam_offset,
              open_heap, closed_set, came_from, current, start, goal, path, gscore):
    # 背景色
    screen.fill((100, 100, 120))
    rows = len(grid)
    cols = len(grid[0])
    
    # 各セルの描画
    for i in range(rows):
        for j in range(cols):
            iso_top = cart_to_iso(j, i, tile_width, tile_height, cam_offset)
            # 通常の地面タイル
            base_color = (160, 160, 180)
            if grid[i][j] == -1:
                # 障害物の場合、地面は暗めに描いてから障害物の立体感を追加
                draw_tile(screen, iso_top, tile_width, tile_height, (120, 120, 140), (80, 80, 100))
                # 簡易的な「立方体」風障害物：中央に小さめの立体感を出す
                center = (iso_top[0], iso_top[1] + tile_height // 4)
                cube_points = [
                    (center[0], center[1] - tile_height // 8),
                    (center[0] + tile_width // 8, center[1]),
                    (center[0], center[1] + tile_height // 8),
                    (center[0] - tile_width // 8, center[1])
                ]
                pygame.draw.polygon(screen, (70, 70, 70), cube_points)
            else:
                draw_tile(screen, iso_top, tile_width, tile_height, base_color, (80, 80, 100))
    
    # 経路（最短経路）の描画：タイル中心を結ぶ線
    if path:
        path_points = []
        for cell in path:
            iso_top = cart_to_iso(cell[1], cell[0], tile_width, tile_height, cam_offset)
            center = (iso_top[0], iso_top[1] + tile_height // 4)
            path_points.append(center)
        if len(path_points) > 1:
            pygame.draw.lines(screen, (50, 205, 50), False, path_points, 4)
    
    # スタート／ゴールマーカー
    for label, cell, col in [('S', start, (0, 128, 0)), ('G', goal, (128, 0, 0))]:
        iso_top = cart_to_iso(cell[1], cell[0], tile_width, tile_height, cam_offset)
        center = (iso_top[0], iso_top[1] + tile_height // 4)
        pygame.draw.circle(screen, col, center, 8)
        font = pygame.font.SysFont("Calibri", 20, bold=True)
        text = font.render(label, True, (255, 255, 255))
        text_rect = text.get_rect(center=center)
        screen.blit(text, text_rect)
    
    # 探索過程の open/closed セットの描画（セル中心に小さな円）
    for cell in closed_set:
        iso_top = cart_to_iso(cell[1], cell[0], tile_width, tile_height, cam_offset)
        center = (iso_top[0], iso_top[1] + tile_height // 4)
        pygame.draw.circle(screen, (255, 165, 0), center, 5)
    for item in open_heap:
        cell = item[1]
        iso_top = cart_to_iso(cell[1], cell[0], tile_width, tile_height, cam_offset)
        center = (iso_top[0], iso_top[1] + tile_height // 4)
        pygame.draw.circle(screen, (0, 206, 209), center, 5)
    if current:
        iso_top = cart_to_iso(current[1], current[0], tile_width, tile_height, cam_offset)
        center = (iso_top[0], iso_top[1] + tile_height // 4)
        pygame.draw.circle(screen, (255, 105, 180), center, 6)

# 線形補間（a から b へ t（0～1）の値で移動）
def interpolate(a, b, t):
    return a + (b - a) * t

# 2つのセル間の中心座標を補間して返す
def interpolate_pos(start_cell, end_cell, t, tile_width, tile_height, cam_offset):
    start_iso = cart_to_iso(start_cell[1], start_cell[0], tile_width, tile_height, cam_offset)
    end_iso = cart_to_iso(end_cell[1], end_cell[0], tile_width, tile_height, cam_offset)
    start_center = (start_iso[0], start_iso[1] + tile_height // 4)
    end_center = (end_iso[0], end_iso[1] + tile_height // 4)
    ix = interpolate(start_center[0], end_center[0], t)
    iy = interpolate(start_center[1], end_center[1], t)
    return int(ix), int(iy)

# 車の描画：簡易的なアイソメトリックカー（ダイヤモンド形）
def draw_car(screen, pos):
    pygame.draw.polygon(screen, (255, 0, 0), [
        (pos[0], pos[1] - 10),
        (pos[0] + 10, pos[1]),
        (pos[0], pos[1] + 10),
        (pos[0] - 10, pos[1])
    ])

def main():
    pygame.init()
    
    # タイルサイズ・グリッドサイズの設定
    tile_width = 60
    tile_height = 40
    rows, cols = 7, 7
    
    screen_width = 800
    screen_height = 600
    screen = pygame.display.set_mode((screen_width, screen_height))
    pygame.display.set_caption("Isometric A* Visualization")
    
    # カメラオフセット：画面中央付近にグリッドが来るように調整
    cam_offset = (screen_width // 2, 100)
    
    # グリッド生成とスタート/ゴールの設定
    grid = generate_grid(rows, cols, obstacle_probability=0.3, cost_min=1, cost_max=5)
    start = (0, 0)
    goal = (rows - 1, cols - 1)
    
    generator = astar_visualize(grid, start, goal)
    finished = False
    path = []
    
    # 車の移動用パラメータ
    car_path = []     # 経路が確定したらセット
    car_progress = 0.0  # 0～1 の補間進捗
    car_segment = 0   # 経路上のセグメント（現在のセル index）
    car_speed = 0.02  # 補間速度（フレームごとの進行量）
    
    clock = pygame.time.Clock()
    
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            # スペースキーでグリッド再生成
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    grid = generate_grid(rows, cols, obstacle_probability=0.3, cost_min=1, cost_max=5)
                    generator = astar_visualize(grid, start, goal)
                    finished = False
                    path = []
                    car_path = []
                    car_progress = 0.0
                    car_segment = 0
        
        # 探索中は探索アルゴリズムのジェネレーターから状態を取得
        if not finished:
            try:
                open_heap, closed_set, came_from, current, finished_flag, gscore, fscore = next(generator)
                if finished_flag:
                    path = reconstruct_path(came_from, goal)
                    finished = True
                    car_path = path[:]  # 経路コピー
            except StopIteration:
                finished = True
        
        # グリッドや探索状態の描画
        draw_grid(screen, grid, tile_width, tile_height, cam_offset,
                  open_heap, closed_set, came_from, current, start, goal, path, gscore)
        
        # 経路が確定している場合、車を経路上で補間させながら描画
        if finished and car_path and len(car_path) >= 2:
            if car_segment < len(car_path) - 1:
                car_progress += car_speed
                if car_progress >= 1.0:
                    car_progress = 0.0
                    car_segment += 1
                car_pos = interpolate_pos(car_path[car_segment], car_path[car_segment + 1],
                                          car_progress, tile_width, tile_height, cam_offset)
                draw_car(screen, car_pos)
            else:
                final_iso = cart_to_iso(car_path[-1][1], car_path[-1][0], tile_width, tile_height, cam_offset)
                final_center = (final_iso[0], final_iso[1] + tile_height // 4)
                draw_car(screen, final_center)
        
        pygame.display.update()
        clock.tick(20)  # フレームレートを20FPSに設定（速度調整用）

if __name__ == "__main__":
    main()
