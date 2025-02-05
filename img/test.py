from PIL import Image, ImageDraw
import math

def locate_corner_points(image, num_points=100):
    width, height = image.size
    center_x, center_y = width // 2, height // 2
    points = []

    # 计算采样点的角度间隔
    angle_step = 360 / num_points

    # 遍历每个角度
    for i in range(num_points):
        angle = i * angle_step
        rad = math.radians(angle)
        
        # 从中心点开始
        x, y = center_x, center_y
        step = 1  # 步长
        
        # 向外扫描直到找到白色像素
        while 0 <= x < width and 0 <= y < height:
            r, g, b, a = image.getpixel((int(x), int(y)))
            # 找到第一个白色像素
            if r == 255 and g == 255 and b == 255 and a > 0:
                points.append((int(x), int(y)))
                break
                
            # 更新坐标
            x = center_x + step * math.cos(rad)
            y = center_y + step * math.sin(rad)
            step += 1

    return points

# 打开外框图片
frame = Image.open("T_Fx_UI_RESONANCE_SlotFairyResonance_01.png").convert("RGBA")

# 定位角点
corner_points = locate_corner_points(frame)

# 创建一个新的图层用于绘制标记
marked_frame = frame.copy()
draw = ImageDraw.Draw(marked_frame)

# 绘制角点标记
for point in corner_points:
    x, y = point
    draw.ellipse((x-3, y-3, x+3, y+3), fill=(255, 0, 0))  # 红色小圆点

# 显示标记后的图像
marked_frame.show()

# 打印所有点的坐标
print("找到的边界点坐标:")
for i, point in enumerate(corner_points):
    print(f"点 {i}: {point}")