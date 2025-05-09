import random
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

# ✅ ここだけ変更すればBox数を調整可能
NUM_BOXES = 80
BIN_SIZE = (10, 10, 10)

class Item:
    def __init__(self, size, name):
        self.size = size
        self.position = None
        self.name = name
        self.color = (random.random(), random.random(), random.random(), 0.6)

    def place(self, pos):
        self.position = pos

    def get_faces(self):
        if self.position is None:
            return []
        x, y, z = self.position
        w, d, h = self.size
        corners = [
            (x, y, z), (x+w, y, z), (x+w, y+d, z), (x, y+d, z),
            (x, y, z+h), (x+w, y, z+h), (x+w, y+d, z+h), (x, y+d, z+h),
        ]
        return [
            [corners[i] for i in [0,1,2,3]],
            [corners[i] for i in [4,5,6,7]],
            [corners[i] for i in [0,1,5,4]],
            [corners[i] for i in [2,3,7,6]],
            [corners[i] for i in [1,2,6,5]],
            [corners[i] for i in [0,3,7,4]],
        ]

def does_fit(bin_size, placed, item, pos):
    x, y, z = pos
    w, d, h = item.size
    if x + w > bin_size[0] or y + d > bin_size[1] or z + h > bin_size[2]:
        return False
    for other in placed:
        ox, oy, oz = other.position
        ow, od, oh = other.size
        if (x < ox + ow and x + w > ox and
            y < oy + od and y + d > oy and
            z < oz + oh and z + h > oz):
            return False
    return True

def pack_items_stepwise(bin_size, items):
    placed = []
    steps = []
    for item in items:
        found = False
        for x in range(bin_size[0]):
            for y in range(bin_size[1]):
                for z in range(bin_size[2]):
                    if does_fit(bin_size, placed, item, (x, y, z)):
                        item.place((x, y, z))
                        placed.append(item)
                        steps.append(list(placed))
                        found = True
                        break
                if found: break
            if found: break
    return steps

def animate_packing(bin_size, steps, filename="3d_packing_demo.gif"):
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    def update(frame):
        ax.cla()
        ax.set_xlim([0, bin_size[1]])  # Yが左右
        ax.set_ylim([0, bin_size[2]])  # Zが奥行き
        ax.set_zlim([0, bin_size[0]])  # Xが高さ（縦）
        ax.set_xlabel('Y')  # 横方向
        ax.set_ylabel('Z')  # 奥行き
        ax.set_zlabel('X')  # 高さ
        ax.set_title(f"Step {frame+1}/{len(steps)}")

        # 視点調整（Xが縦になるような角度）
        ax.view_init(elev=30, azim=120)

        items = steps[frame]
        for item in items:
            # 描画位置変換（X→Z, Y→X, Z→Y にする）
            x, y, z = item.position
            w, d, h = item.size
            # swap X, Y, Z axes: new_x = y, new_y = z, new_z = x
            item_rotated = Item((d, h, w), item.name)
            item_rotated.place((y, z, x))
            item_rotated.color = item.color
            faces = item_rotated.get_faces()
            ax.add_collection3d(
                Poly3DCollection(faces, facecolors=item.color, linewidths=1, edgecolors='black')
            )

    ani = FuncAnimation(fig, update, frames=len(steps), repeat=False)
    ani.save(filename, writer='pillow', fps=2)
    plt.close()


# -----------------------------
# 実行
items = [
    Item((random.randint(1, 3), random.randint(1, 3), random.randint(1, 3)), f"Item{i}")
    for i in range(NUM_BOXES)
]

steps = pack_items_stepwise(BIN_SIZE, items)
animate_packing(BIN_SIZE, steps, filename="3d_packing_demo.gif")

print(f"✅ 完了: {NUM_BOXES}個のBoxのPacking GIFを作成しました（3d_packing_demo.gif）")
