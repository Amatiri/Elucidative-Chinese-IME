import os

# 项目根目录（本文件所在目录）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据文件路径
DATA_FILE = os.path.join(BASE_DIR, "dictionary.txt")
DATA_NO_NUMBER_FILE = os.path.join(BASE_DIR, "dictionary_no_number.txt")
CIYU_FILE = os.path.join(BASE_DIR, "ciyu.txt")

# 编码相关常量
CODE_CHARS = "1234567890qwertyuiopasdfghjklzxcvbnm;'."
SURROUND_CHARS = "1234567890qwertyuiopasdfghjklzxcvbnm;'.-= "
SELECTION_SYMBOLS = ["!", "@", "#", "$", "%"]
SYMBOL_TO_INDEX = {"!": 0, "@": 1, "#": 2, "$": 3, "%": 4}

# ===== 字体配置 =====
FONT_PRIMARY_PREFERRED = "方正硬笔行书简繁"   # 优先字体（系统有此字体时使用）
FONT_PRIMARY_FALLBACK = "华文中宋"           # 保底字体
FONT_SMALL_NAME = "黑体"
FONT_BUTTON_NAME = "楷体"

FONT_SIZE_INPUT = 13       # 输入框 + 候选 + 多字预览
FONT_SIZE_COUNT = 14       # 词条计数
FONT_SIZE_RADICAL = 11     # 部首表
FONT_SIZE_SMALL = 8        # 页码
FONT_SIZE_BUTTON = 14      # 设置按钮


def get_primary_font_name(tk_root=None):
    """检测系统是否有优先字体，有则返回，无则返回保底字体。

    传入已有 Tk 根窗口可避免重复创建 Tk 实例；
    不传则内部创建临时 Tk 实例（仅用于无 GUI 的脚本场景）。
    """
    import tkinter.font as tkfont
    root = tk_root
    destroy_later = False
    if root is None:
        import tkinter as tk
        root = tk.Tk()
        destroy_later = True
    try:
        available = set(tkfont.families(root=root))
        if FONT_PRIMARY_PREFERRED in available:
            return FONT_PRIMARY_PREFERRED
        return FONT_PRIMARY_FALLBACK
    finally:
        if destroy_later:
            root.destroy()
