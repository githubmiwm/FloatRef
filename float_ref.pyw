import sys
import os
import logging
import subprocess
import random
import json
import math
import ctypes
from ctypes import wintypes

from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QGraphicsOpacityEffect, 
                             QListWidget, QListWidgetItem, QSlider, QAbstractItemView,
                             QScrollArea, QFrame, QSystemTrayIcon, QMenu, QMessageBox,
                             QDialog, QTextEdit, QInputDialog, QSpinBox, QCheckBox, QDialogButtonBox, QComboBox, QGroupBox, QStyle)
from PyQt6.QtGui import (QPixmap, QPainter, QPen, QColor, QFont, QCursor, QIcon, 
                         QAction, QActionGroup, QImageReader, QImage, QPolygon)
from PyQt6.QtCore import (Qt, QSize, QRect, QPoint, QPointF, QRectF, QTimer, pyqtSignal, QObject,
                          QPropertyAnimation, QEasingCurve, QParallelAnimationGroup,
                          QVariantAnimation, QAbstractAnimation, QSettings, QThreadPool, QRunnable, pyqtSlot)

# ---------------------------------------------------------
# Windows API Constants & Setup (Strict Typing)
# ---------------------------------------------------------
user32 = ctypes.windll.user32

# 定数定義
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008

# 型定義の強化 (64bit対応)
try:
    HWND_TOPMOST = ctypes.c_void_p(-1)
    HWND_NOTOPMOST = ctypes.c_void_p(-2)
    HWND_TOP = ctypes.c_void_p(0)
    HWND_BOTTOM = ctypes.c_void_p(1)
except Exception:
    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2
    HWND_TOP = 0
    HWND_BOTTOM = 1

# 関数の引数と戻り値の型を明示的に定義
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, 
    ctypes.c_int, ctypes.c_int, ctypes.c_uint
]
user32.SetWindowPos.restype = wintypes.BOOL

try:
    GetWindowLongPtr = user32.GetWindowLongPtrW
    GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
    GetWindowLongPtr.restype = ctypes.c_longlong
except AttributeError:
    GetWindowLongPtr = user32.GetWindowLongW
    GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
    GetWindowLongPtr.restype = ctypes.c_long

def get_window_ex_style(hwnd):
    return GetWindowLongPtr(hwnd, GWL_EXSTYLE)

def set_window_on_top_native(hwnd, on_top=True):
    """Windows APIを使ってウィンドウの最前面状態を切り替える"""
    
    # ハンドルがint型で来てもctypesのHWND型に変換
    hwnd_c = wintypes.HWND(int(hwnd))

    target_z_order = HWND_TOPMOST if on_top else HWND_NOTOPMOST
    
    # API実行
    user32.SetWindowPos(hwnd_c, target_z_order, 0, 0, 0, 0, 
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)

# ---------------------------------------------------------
# Logging Setup (Generic)
# ---------------------------------------------------------
def setup_logging():
    log_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug.log')
    # filemode='w' で起動ごとにログをクリア（上書き）
    logging.basicConfig(
        level=logging.DEBUG,
        filename=log_filename,
        filemode='w', 
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger('').addHandler(console)

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    sys.excepthook = handle_exception

setup_logging()
logging.info("Application starting... (Log cleared)")

# ---------------------------------------------------------
# Startup Shortcut Helper
# ---------------------------------------------------------
def set_startup_link(enable=True):
    try:
        startup_dir = os.path.join(os.getenv('APPDATA'), r'Microsoft\Windows\Start Menu\Programs\Startup')
        link_path = os.path.join(startup_dir, "FloatRef.lnk")
        
        if not enable:
            if os.path.exists(link_path):
                os.remove(link_path)
            return

        target = sys.executable.replace("python.exe", "pythonw.exe")
        script = os.path.abspath(__file__)
        work_dir = os.path.dirname(script)
        
        vbs_script = (
            'Set oWS = WScript.CreateObject("WScript.Shell")\n'
            f'Set oLink = oWS.CreateShortcut("{link_path}")\n'
            f'oLink.TargetPath = "{target}"\n'
            f'oLink.Arguments = Chr(34) & "{script}" & Chr(34)\n'
            f'oLink.WorkingDirectory = "{work_dir}"\n'
            'oLink.Save'
        )
        
        vbs_path = os.path.join(work_dir, "create_shortcut.vbs")
        with open(vbs_path, "w") as f:
            f.write(vbs_script)
        
        subprocess.run(["cscript", "//Nologo", vbs_path], check=True)
        os.remove(vbs_path)
        
    except Exception as e:
        logging.error(f"Failed to set startup: {e}")

def is_startup_enabled():
    startup_dir = os.path.join(os.getenv('APPDATA'), r'Microsoft\Windows\Start Menu\Programs\Startup')
    link_path = os.path.join(startup_dir, "FloatRef.lnk")
    return os.path.exists(link_path)

# ---------------------------------------------------------
# Worker Signals & Threads
# ---------------------------------------------------------
class WorkerSignals(QObject):
    finished = pyqtSignal(str, QImage)

class ThumbnailWorker(QRunnable):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            reader = QImageReader(self.path)
            reader.setAutoTransform(True)
            orig_size = reader.size()
            target_size = 600
            
            if orig_size.width() > target_size or orig_size.height() > target_size:
                reader.setScaledSize(orig_size.scaled(target_size, target_size, Qt.AspectRatioMode.KeepAspectRatio))
            
            img = reader.read()
            if not img.isNull():
                self.signals.finished.emit(self.path, img)
        except Exception:
            pass

# ---------------------------------------------------------
# Image Data Manager
# ---------------------------------------------------------
class ImageStackManager(QObject):
    thumbnail_updated = pyqtSignal(str) 

    def __init__(self):
        super().__init__()
        self.image_paths = []
        self._pixmap_cache = {} 
        self._small_cache = {} 
        self._large_cache = {} 
        
        self.thread_pool = QThreadPool()
        self.loading_paths = set()
        self.settings = QSettings("Tokitoma", "FloatRef")
        
        self.load_from_settings()

    def add_image(self, path):
        if path not in self.image_paths:
            self.image_paths.append(path)
            self.save_to_settings()

    def save_to_settings(self):
        self.settings.setValue("image_paths", json.dumps(self.image_paths))

    def load_from_settings(self):
        json_str = self.settings.value("image_paths", "[]")
        if isinstance(json_str, str):
            try:
                paths = json.loads(json_str)
                valid_paths = [p for p in paths if os.path.exists(p)]
                self.image_paths = valid_paths
            except json.JSONDecodeError:
                self.image_paths = []
        else:
            self.image_paths = []

    def clear_images(self):
        self.image_paths = []
        self._pixmap_cache = {}
        self._small_cache = {}
        self._large_cache = {}
        self.save_to_settings()

    def get_pixmap(self, path):
        if path in self._pixmap_cache:
            return self._pixmap_cache[path]
        
        try:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            s = reader.size()
            if s.width() > 3840 or s.height() > 3840:
                reader.setScaledSize(s.scaled(3840, 3840, Qt.AspectRatioMode.KeepAspectRatio))
                
            img = reader.read()
            if not img.isNull():
                pix = QPixmap.fromImage(img)
                self._pixmap_cache[path] = pix
                return pix
        except Exception:
            pass
        return QPixmap()

    def get_icon(self, path, for_list=False):
        if for_list and path in self._large_cache:
            return self._large_cache[path]
        
        if path in self._small_cache:
            if for_list and path not in self.loading_paths:
                self.start_loading_large(path)
            return self._small_cache[path]

        try:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            reader.setScaledSize(reader.size().scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio))
            img = reader.read()
            
            if not img.isNull():
                pix = QPixmap.fromImage(img)
                icon = QIcon(pix)
                self._small_cache[path] = icon
                if path not in self.loading_paths:
                    self.start_loading_large(path)
                return icon
        except Exception:
            pass
        return QIcon()

    def start_loading_large(self, path):
        if path in self._large_cache or path in self.loading_paths:
            return
        self.loading_paths.add(path)
        worker = ThumbnailWorker(path)
        worker.signals.finished.connect(self.on_large_thumbnail_ready)
        self.thread_pool.start(worker)

    def on_large_thumbnail_ready(self, path, image):
        if path in self.loading_paths:
            self.loading_paths.remove(path)
        if not image.isNull():
            pix = QPixmap.fromImage(image)
            icon = QIcon(pix)
            self._large_cache[path] = icon
            self.thumbnail_updated.emit(path)

stack_manager = ImageStackManager()

# ---------------------------------------------------------
# Translation Dictionary
# ---------------------------------------------------------
TRANSLATIONS = {
    'ja': {
        'settings_title': '設定',
        'slideshow_group': 'スライドショー',
        'active': 'スライドショーを有効にする',
        'random': 'ランダムに表示',
        'interval': '切り替え間隔:',
        'interval_suffix': ' 秒',
        'fade': 'フェード時間:',
        'fade_suffix': ' 秒',
        'view_group': '表示設定',
        'layer': '表示レイヤー:',
        'layer_top': '常に前面',
        'layer_normal': '通常のウィンドウ',
        'layer_bottom': '常に背面',
        'thumb_pos': 'サムネイル位置:',
        'pos_top': '上',
        'pos_bottom': '下',
        'anchor_group': '画像配置の起点',
        'anchor_center': '中央',
        'anchor_top_left': '左上',
        'anchor_top_right': '右上',
        'anchor_bottom_left': '左下',
        'anchor_bottom_right': '右下',
        'show_carousel': 'サムネイルを表示する',
        'btn_group': 'スイッチボタン設定',
        'btn_visible': 'スイッチボタンを表示する',
        'btn_size': 'ボタンサイズ:',
        'btn_opacity': 'ボタン透明度:',
        'sys_group': 'システム',
        'startup': 'スタートアップに登録',
        'reset_btn': '初期設定にリセット',
        'menu_new_slot': 'スロットを追加する',
        'menu_toggle': '非表示/再表示',
        'menu_arrange': '全体を調整して整列',
        'menu_lock': '操作ロック',
        'menu_close_all': 'すべて閉じる',
        'menu_reset': 'すべて最初から',
        'menu_settings': '設定...',
        'menu_layer': '表示レイヤー',
        'menu_help': 'ヘルプ',
        'menu_quit': '終了',
        'menu_view_list': '一覧リストを表示',
        'menu_toggle_carousel': 'サムネイルの表示/非表示',
        'menu_show_switch_btn': 'スイッチボタンを表示',
        'msg_close_title': '確認',
        'msg_close_text': 'すべての画像を閉じますか？\n（履歴は保持されます）',
        'msg_reset_title': '確認',
        'msg_reset_text': 'すべての画像と設定をリセットして初期状態に戻しますか？\n（この操作は取り消せません）',
        'help_title': 'FloatRef - ヘルプ',
        'btn_fit_hint': '枠に合わせて画像全体を表示',
        'btn_trim_hint': '画像サイズに枠を合わせる',
        'btn_list_hint': '一覧表示モードへ切り替え',
        'resize_hint': '左ドラッグ：画像と枠をリサイズ（アスペクト維持）\n右ドラッグ：枠のみトリミング\n中ドラッグ：画像を移動\nホイール：カーソル位置でズーム',
        'drop_text': 'Drop here',
        'language': '言語 (Language):',
        'slot_add': 'スロットを追加',
        'slot_move_back': 'モニター外の表示を戻す'
    },
    'en': {
        'settings_title': 'Settings',
        'slideshow_group': 'Slideshow',
        'active': 'Enable Slideshow',
        'random': 'Random Order',
        'interval': 'Interval:',
        'interval_suffix': ' s',
        'fade': 'Fade Duration:',
        'fade_suffix': ' s',
        'view_group': 'View Settings',
        'layer': 'Layer Mode:',
        'layer_top': 'Always on Top',
        'layer_normal': 'Normal Window',
        'layer_bottom': 'Always at Bottom',
        'thumb_pos': 'Thumbnail Pos:',
        'pos_top': 'Top',
        'pos_bottom': 'Bottom',
        'anchor_group': 'Image Anchor',
        'anchor_center': 'Center',
        'anchor_top_left': 'Top-Left',
        'anchor_top_right': 'Top-Right',
        'anchor_bottom_left': 'Bottom-Left',
        'anchor_bottom_right': 'Bottom-Right',
        'show_carousel': 'Show Thumbnails',
        'btn_group': 'Switch Button Settings',
        'btn_visible': 'Show Switch Button',
        'btn_size': 'Button Size:',
        'btn_opacity': 'Button Opacity:',
        'sys_group': 'System',
        'startup': 'Run at Startup',
        'reset_btn': 'Reset to Default',
        'menu_new_slot': 'Add New Slot',
        'menu_toggle': 'Show/Hide All',
        'menu_arrange': 'Arrange All (Tiled)',
        'menu_lock': 'Lock Controls',
        'menu_close_all': 'Close All Images',
        'menu_reset': 'Reset Application',
        'menu_settings': 'Settings...',
        'menu_layer': 'Layer Mode',
        'menu_help': 'Help',
        'menu_quit': 'Quit',
        'menu_view_list': 'Show List View',
        'menu_toggle_carousel': 'Show/Hide Thumbnails',
        'menu_show_switch_btn': 'Show Switch Button',
        'msg_close_title': 'Confirm',
        'msg_close_text': 'Close all images?\n(History will be kept)',
        'msg_reset_title': 'Confirm',
        'msg_reset_text': 'Reset all images and settings to default?\n(This cannot be undone)',
        'help_title': 'FloatRef - Help',
        'btn_fit_hint': 'Fit image to window',
        'btn_trim_hint': 'Resize window to image',
        'btn_list_hint': 'Switch to list view',
        'resize_hint': 'L-Drag: Resize Window & Image\nR-Drag: Crop Frame only\nM-Drag: Pan Image\nWheel: Zoom at cursor',
        'drop_text': 'Drop here',
        'language': 'Language:',
        'slot_add': 'Add Slot',
        'slot_move_back': 'Bring back from off-screen'
    }
}

# ---------------------------------------------------------
# Switch Button
# ---------------------------------------------------------
class SwitchButton(QWidget):
    toggled = pyqtSignal()

    def __init__(self, size=40, opacity=0.5, parent=None, manager=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.ToolTip)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self._size = size
        self.drag_pos = None
        self.setFixedSize(size, size)
        self.setWindowOpacity(opacity)
        
        self.drag_start_global = QPoint()
        self.is_dragging = False

    def set_properties(self, size, opacity):
        self._size = size
        self.setFixedSize(size, size)
        self.setWindowOpacity(opacity)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggled.emit()
        elif event.button() == Qt.MouseButton.RightButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.drag_start_global = event.globalPosition().toPoint()
            self.is_dragging = False

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.RightButton and self.drag_pos:
            curr_pos = event.globalPosition().toPoint()
            # 一定距離以上動いたらドラッグとみなす
            if (curr_pos - self.drag_start_global).manhattanLength() > 5:
                self.is_dragging = True
                self.move(curr_pos - self.drag_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            if not self.is_dragging:
                # ドラッグでなければメニュー表示
                if self.manager:
                    self.manager.tray_menu.exec(event.globalPosition().toPoint())
        self.drag_pos = None
        self.is_dragging = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        painter.setBrush(QColor(255, 255, 255, 255))
        pen = QPen(QColor(0, 0, 0, 128))
        pen.setWidth(3)
        painter.setPen(pen)
        rect = self.rect().adjusted(2, 2, -2, -2)
        painter.drawEllipse(rect)

# ---------------------------------------------------------
# Custom Dialog for Settings
# ---------------------------------------------------------
class SlideshowSettingsDialog(QDialog):
    def __init__(self, params, get_text_func, parent=None):
        super().__init__(parent)
        self.get_text = get_text_func
        self.setWindowTitle(self.get_text('settings_title'))
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(320)
        self.reset_requested = False 
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        h_lang = QHBoxLayout()
        h_lang.addWidget(QLabel(self.get_text('language')))
        self.combo_lang = QComboBox()
        self.combo_lang.addItem("日本語", "ja")
        self.combo_lang.addItem("English", "en")
        current_lang = params.get('language', 'ja')
        idx = self.combo_lang.findData(current_lang)
        if idx >= 0: self.combo_lang.setCurrentIndex(idx)
        h_lang.addWidget(self.combo_lang)
        h_lang.addStretch()
        layout.addLayout(h_lang)

        grp_slide = QGroupBox(self.get_text('slideshow_group'))
        v_slide = QVBoxLayout()
        self.chk_active = QCheckBox(self.get_text('active'))
        self.chk_active.setChecked(params['active'])
        v_slide.addWidget(self.chk_active)
        self.chk_random = QCheckBox(self.get_text('random'))
        self.chk_random.setChecked(params['random'])
        v_slide.addWidget(self.chk_random)
        h_interval = QHBoxLayout()
        h_interval.addWidget(QLabel(self.get_text('interval')))
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 3600)
        self.spin_interval.setValue(params['interval'])
        self.spin_interval.setSuffix(self.get_text('interval_suffix'))
        h_interval.addWidget(self.spin_interval)
        v_slide.addLayout(h_interval)
        v_fade = QVBoxLayout()
        h_fade_label = QHBoxLayout()
        h_fade_label.addWidget(QLabel(self.get_text('fade')))
        self.label_fade_val = QLabel(f"{params['fade']:.1f}" + self.get_text('fade_suffix'))
        h_fade_label.addWidget(self.label_fade_val)
        h_fade_label.addStretch()
        v_fade.addLayout(h_fade_label)
        self.slider_fade = QSlider(Qt.Orientation.Horizontal)
        self.slider_fade.setRange(0, 50) 
        self.slider_fade.setValue(int(params['fade'] * 10))
        self.slider_fade.valueChanged.connect(lambda v: self.label_fade_val.setText(f"{v/10.0:.1f}" + self.get_text('fade_suffix')))
        v_fade.addWidget(self.slider_fade)
        v_slide.addLayout(v_fade)
        grp_slide.setLayout(v_slide)
        layout.addWidget(grp_slide)

        grp_view = QGroupBox(self.get_text('view_group'))
        v_view = QVBoxLayout()
        h_layer = QHBoxLayout()
        h_layer.addWidget(QLabel(self.get_text('layer')))
        self.combo_layer = QComboBox()
        self.combo_layer.addItems([self.get_text('layer_top'), self.get_text('layer_normal'), self.get_text('layer_bottom')])
        layer_map = {'top': 0, 'normal': 1, 'bottom': 2}
        self.combo_layer.setCurrentIndex(layer_map.get(params['layer_mode'], 1))
        h_layer.addWidget(self.combo_layer)
        v_view.addLayout(h_layer)
        
        h_anchor = QHBoxLayout()
        h_anchor.addWidget(QLabel(self.get_text('anchor_group')))
        self.combo_anchor = QComboBox()
        anchors = [
            ('center', 'anchor_center'),
            ('top-left', 'anchor_top_left'),
            ('top-right', 'anchor_top_right'),
            ('bottom-left', 'anchor_bottom_left'),
            ('bottom-right', 'anchor_bottom_right')
        ]
        for key, text_key in anchors:
            self.combo_anchor.addItem(self.get_text(text_key), key)
            
        current_anchor = params.get('anchor_mode', 'center')
        idx = self.combo_anchor.findData(current_anchor)
        if idx >= 0: self.combo_anchor.setCurrentIndex(idx)
        else: self.combo_anchor.setCurrentIndex(0)
        
        h_anchor.addWidget(self.combo_anchor)
        v_view.addLayout(h_anchor)
        
        h_thumb = QHBoxLayout()
        h_thumb.addWidget(QLabel(self.get_text('thumb_pos')))
        self.combo_thumb = QComboBox()
        self.combo_thumb.addItems([self.get_text('pos_top'), self.get_text('pos_bottom')])
        self.combo_thumb.setCurrentIndex(0 if params['carousel_pos'] == 'top' else 1)
        h_thumb.addWidget(self.combo_thumb)
        v_view.addLayout(h_thumb)
        self.chk_show_carousel = QCheckBox(self.get_text('show_carousel'))
        self.chk_show_carousel.setChecked(params['show_carousel'])
        v_view.addWidget(self.chk_show_carousel)
        grp_view.setLayout(v_view)
        layout.addWidget(grp_view)

        grp_btn = QGroupBox(self.get_text('btn_group'))
        v_btn = QVBoxLayout()
        self.chk_btn_visible = QCheckBox(self.get_text('btn_visible'))
        self.chk_btn_visible.setChecked(params['btn_visible'])
        v_btn.addWidget(self.chk_btn_visible)
        
        v_btn_size = QVBoxLayout()
        h_btn_size_label = QHBoxLayout()
        h_btn_size_label.addWidget(QLabel(self.get_text('btn_size')))
        self.label_size_val = QLabel(f"{params['btn_size']} px")
        h_btn_size_label.addWidget(self.label_size_val)
        h_btn_size_label.addStretch()
        v_btn_size.addLayout(h_btn_size_label)
        self.slider_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_size.setRange(1, 20) 
        self.slider_size.setValue(int(params['btn_size'] / 10))
        self.slider_size.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider_size.setTickInterval(1)
        self.slider_size.valueChanged.connect(lambda v: self.label_size_val.setText(f"{v * 10} px"))
        v_btn_size.addWidget(self.slider_size)
        v_btn.addLayout(v_btn_size)
        
        v_opacity = QVBoxLayout()
        h_op_label = QHBoxLayout()
        h_op_label.addWidget(QLabel(self.get_text('btn_opacity')))
        self.label_op_val = QLabel(f"{int(params['btn_opacity'] * 100)}%")
        h_op_label.addWidget(self.label_op_val)
        h_op_label.addStretch()
        v_opacity.addLayout(h_op_label)
        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(0, 4) 
        self.slider_opacity.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider_opacity.setTickInterval(1)
        current_op_step = int(params['btn_opacity'] * 4)
        self.slider_opacity.setValue(current_op_step)
        self.slider_opacity.valueChanged.connect(lambda v: self.label_op_val.setText(f"{v * 25}%"))
        v_opacity.addWidget(self.slider_opacity)
        v_btn.addLayout(v_opacity)
        
        grp_btn.setLayout(v_btn)
        layout.addWidget(grp_btn)

        self.chk_startup = QCheckBox(self.get_text('startup'))
        self.chk_startup.setChecked(params['startup'])
        layout.addWidget(self.chk_startup)
        
        layout.addSpacing(10)

        hbox_btns = QHBoxLayout()
        btn_reset = QPushButton(self.get_text('reset_btn'))
        btn_reset.clicked.connect(self.reset_form)
        hbox_btns.addWidget(btn_reset)
        hbox_btns.addStretch()
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        hbox_btns.addWidget(btns)
        
        layout.addLayout(hbox_btns)
        self.adjustSize() 

    def reset_form(self):
        self.chk_active.setChecked(False)
        self.chk_random.setChecked(False)
        self.spin_interval.setValue(10)
        self.slider_fade.setValue(10) 
        self.combo_layer.setCurrentIndex(1) 
        self.combo_anchor.setCurrentIndex(0) 
        self.combo_thumb.setCurrentIndex(0) 
        self.chk_show_carousel.setChecked(True) 
        self.chk_btn_visible.setChecked(False)
        self.slider_size.setValue(4) 
        self.slider_opacity.setValue(2) 
        self.chk_startup.setChecked(False)
        self.reset_requested = True

    def get_values(self):
        layer_indices = {0: 'top', 1: 'normal', 2: 'bottom'}
        return {
            'language': self.combo_lang.currentData(),
            'interval': self.spin_interval.value(),
            'active': self.chk_active.isChecked(),
            'random': self.chk_random.isChecked(),
            'fade': self.slider_fade.value() / 10.0,
            'layer_mode': layer_indices[self.combo_layer.currentIndex()],
            'anchor_mode': self.combo_anchor.currentData(), 
            'carousel_pos': 'top' if self.combo_thumb.currentIndex() == 0 else 'bottom',
            'show_carousel': self.chk_show_carousel.isChecked(),
            'btn_visible': self.chk_btn_visible.isChecked(),
            'btn_size': self.slider_size.value() * 10,
            'btn_opacity': self.slider_opacity.value() * 0.25,
            'startup': self.chk_startup.isChecked(),
            'reset_requested': self.reset_requested
        }

# ---------------------------------------------------------
# Window Manager
# ---------------------------------------------------------
class WindowManager:
    def __init__(self):
        self.windows = []
        self.settings = QSettings("Tokitoma", "FloatRef")
        self.is_locked = False 
        
        saved_layer = self.settings.value("layer_mode", "normal") 
        if self.settings.contains("is_on_top"):
            old_bool = self.settings.value("is_on_top", True, type=bool)
            saved_layer = 'top' if old_bool else 'bottom'
            self.settings.remove("is_on_top")
            self.settings.setValue("layer_mode", saved_layer)

        self.params = {
            'language': self.settings.value("language", "ja"),
            'interval': self.settings.value("slideshow_interval", 10, type=int),
            'active': self.settings.value("slideshow_active", False, type=bool),
            'random': self.settings.value("slideshow_random", False, type=bool),
            'fade': float(self.settings.value("fade_duration", 1.0)),
            'layer_mode': saved_layer,
            'anchor_mode': self.settings.value("anchor_mode", 'center'), 
            'carousel_pos': self.settings.value("carousel_pos", 'top'),
            'show_carousel': self.settings.value("show_carousel", True, type=bool),
            'btn_visible': self.settings.value("btn_visible", False, type=bool),
            'btn_size': self.settings.value("btn_size", 40, type=int),
            'btn_opacity': float(self.settings.value("btn_opacity", 0.5)),
            'startup': is_startup_enabled()
        }
        
        self.last_index = self.settings.value("last_index", 0, type=int)

        self.switch_button = SwitchButton(self.params['btn_size'], self.params['btn_opacity'], manager=self)
        if self.settings.value("btn_pos"):
            self.switch_button.move(self.settings.value("btn_pos"))
        else:
            self.switch_button.move(100, 100)
            
        self.switch_button.toggled.connect(self.toggle_all_visibility)
        if self.params['btn_visible']:
            self.switch_button.show()
        else:
            self.switch_button.hide()
        
        try:
            self.app_icon = self.load_app_icon()
            self.tray_icon = QSystemTrayIcon()
            self.tray_icon.setIcon(self.app_icon)
            self.tray_menu = QMenu()
            
            self.act_new = QAction(self.tr('menu_new_slot'), self.tray_menu)
            self.act_new.triggered.connect(lambda: self.create_window(next_image=True))
            self.tray_menu.addAction(self.act_new)
            
            self.act_toggle = QAction(self.tr('menu_toggle'), self.tray_menu)
            self.act_toggle.triggered.connect(self.toggle_all_visibility)
            self.tray_menu.addAction(self.act_toggle)

            self.act_arrange = QAction(self.tr('menu_arrange'), self.tray_menu)
            self.act_arrange.triggered.connect(self.arrange_windows_tiled)
            self.tray_menu.addAction(self.act_arrange)

            self.act_lock = QAction(self.tr('menu_lock'), self.tray_menu, checkable=True)
            self.act_lock.triggered.connect(self.toggle_operation_lock)
            self.tray_menu.addAction(self.act_lock)

            self.act_close_all = QAction(self.tr('menu_close_all'), self.tray_menu)
            self.act_close_all.triggered.connect(self.confirm_close_all_images)
            self.tray_menu.addAction(self.act_close_all)

            self.act_reset = QAction(self.tr('menu_reset'), self.tray_menu)
            self.act_reset.triggered.connect(self.reset_application)
            self.tray_menu.addAction(self.act_reset)

            self.tray_menu.addSeparator()

            self.act_settings = QAction(self.tr('menu_settings'), self.tray_menu)
            self.act_settings.triggered.connect(self.open_settings)
            self.tray_menu.addAction(self.act_settings)
            
            self.tray_menu.addSeparator()
            
            self.act_help = QAction(self.tr('menu_help'), self.tray_menu)
            self.act_help.triggered.connect(self.show_help)
            self.tray_menu.addAction(self.act_help)
            
            self.tray_menu.addSeparator()
            
            self.act_quit = QAction(self.tr('menu_quit'), self.tray_menu)
            self.act_quit.triggered.connect(self.close_all)
            self.tray_menu.addAction(self.act_quit)
            
            self.set_global_layer(self.params['layer_mode'])
            
            self.tray_icon.setContextMenu(self.tray_menu)
            self.tray_icon.activated.connect(self.on_tray_activated)
            self.tray_icon.show()
            
            self.restore_window_states()

        except Exception as e:
            logging.error(f"Error initializing WindowManager: {e}")
            raise e

    def tr(self, key):
        lang = self.params.get('language', 'ja')
        if lang not in TRANSLATIONS: lang = 'ja'
        return TRANSLATIONS[lang].get(key, key)

    def retranslate_ui(self):
        self.act_new.setText(self.tr('menu_new_slot'))
        self.act_toggle.setText(self.tr('menu_toggle'))
        self.act_arrange.setText(self.tr('menu_arrange'))
        self.act_lock.setText(self.tr('menu_lock'))
        self.act_close_all.setText(self.tr('menu_close_all'))
        self.act_reset.setText(self.tr('menu_reset'))
        self.act_settings.setText(self.tr('menu_settings'))
        self.act_help.setText(self.tr('menu_help'))
        self.act_quit.setText(self.tr('menu_quit'))
        
        for w in self.windows:
            w.update_text()

    def load_app_icon(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_dir, "icon.png")
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        else:
            pix = QPixmap(64, 64)
            pix.fill(QColor(100, 100, 100))
            return QIcon(pix)

    def bring_switch_to_front(self):
        if self.switch_button.isVisible():
            self.switch_button.raise_()

    def suspend_layers(self):
        # ログ削除: logging.info("Suspending always-on-top for dialog using native API.")
        for w in self.windows:
            hwnd = int(w.winId())
            set_window_on_top_native(hwnd, False)
        if self.switch_button.isVisible():
            hwnd_btn = int(self.switch_button.winId())
            set_window_on_top_native(hwnd_btn, False)

    def restore_layers(self):
        # ログ削除: logging.info("Restoring original layer settings using native API.")
        is_top = (self.params['layer_mode'] == 'top')
        for w in self.windows:
            hwnd = int(w.winId())
            if is_top:
                set_window_on_top_native(hwnd, True)
            else:
                set_window_on_top_native(hwnd, False)
        if self.switch_button.isVisible():
            hwnd_btn = int(self.switch_button.winId())
            set_window_on_top_native(hwnd_btn, True)
            self.switch_button.raise_()

    def create_window(self, pos=None, size=None, next_image=False):
        if next_image and self.windows:
            idx = self.windows[-1].current_index + 1
        elif not self.windows:
            idx = self.last_index
        else:
            idx = self.windows[-1].current_index

        new_window = ImageSlot(image_index=idx, manager=self)
        
        new_window.set_layer_mode(self.params['layer_mode'])
        safe_fade = min(self.params['fade'], max(0, self.params['interval'] - 0.1))
        new_window.set_slideshow_params(self.params['interval'] * 1000, self.params['random'])
        new_window.set_fade_duration(safe_fade)
        new_window.set_carousel_position(self.params['carousel_pos'])
        new_window.set_locked(self.is_locked)

        if stack_manager.image_paths:
             new_window.update_image_source()

        if self.params['active']:
            new_window.start_slideshow()

        if pos:
            new_window.move(pos)
        else:
            if self.windows:
                last_win = self.windows[-1]
                new_window.move(last_win.pos() + QPoint(30, 30))
                if not next_image:
                    new_window.current_index = last_win.current_index
                    new_window.update_image_source()
        
        if size:
            new_window.resize(size)

        new_window.show()
        self.windows.append(new_window)
        self.bring_switch_to_front()
        return new_window

    def open_multiple_windows(self, items):
        # リスト選択時は自動整列させず、リスト上の位置から拡大表示する
        for index, rect in items:
            win = self.create_window(pos=rect.topLeft(), size=rect.size())
            win.current_index = index
            win.update_image_source()
            
            if win.pixmap:
                win.calculate_fit_scale()
                win.resize_window_to_image_size()
                
                # 中心から広がるように配置
                center = rect.center()
                geo = win.geometry()
                new_x = center.x() - (geo.width() // 2)
                new_y = center.y() - (geo.height() // 2)
                win.move(new_x, new_y)
                win.move_inside_screen()
                
        self.bring_switch_to_front()

    def arrange_windows_tiled(self):
        if not self.windows: return
        screen = QApplication.primaryScreen().availableGeometry()
        count = len(self.windows)
        cols = math.ceil(math.sqrt(count))
        rows = math.ceil(count / cols)
        
        # 画面サイズベースのセルサイズ（最大）
        cell_w = screen.width() // cols
        cell_h = screen.height() // rows

        # 縮小率の計算
        min_ratio = 1.0
        
        for win in self.windows:
            w, h = win.width(), win.height()
            r_w = cell_w / w if w > cell_w else 1.0
            r_h = cell_h / h if h > cell_h else 1.0
            ratio = min(r_w, r_h)
            if ratio < min_ratio:
                min_ratio = ratio

        # 適用
        for i, win in enumerate(self.windows):
            r = i // cols
            c = i % cols
            
            # 配置位置（左上基準）
            base_x = screen.left() + c * cell_w
            base_y = screen.top() + r * cell_h
            
            # 新しいサイズ
            new_w = int(win.width() * min_ratio)
            new_h = int(win.height() * min_ratio)
            
            # 中央寄せ座標
            target_x = base_x + (cell_w - new_w) // 2
            target_y = base_y + (cell_h - new_h) // 2
            
            # ウィンドウサイズ更新
            win.setGeometry(target_x, target_y, new_w, new_h)
            
            # 画像の見た目（スケールとオフセット）も縮小率に合わせて更新
            if win.pixmap:
                win.scale_factor *= min_ratio
                win.img_offset *= min_ratio
            
            win.update_satellites()
        
        self.bring_switch_to_front()

    def on_window_closed(self, window):
        if window in self.windows:
            self.windows.remove(window)

    def set_global_layer(self, mode):
        self.params['layer_mode'] = mode
        self.settings.setValue("layer_mode", mode) 
        for w in self.windows:
            w.set_layer_mode(mode)
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.ToolTip
        self.switch_button.setWindowFlags(flags)
        if self.params['btn_visible']:
            self.switch_button.show()
        self.update_layer_menu_check()

    def update_layer_menu_check(self):
        pass # メニュー項目削除により何もしない

    def toggle_all_visibility(self):
        any_visible = any(w.isVisible() for w in self.windows)
        if any_visible:
            self.hide_all_windows()
        else:
            self.show_hidden_windows()

    def toggle_global_carousel(self):
        # カルーセルの表示設定をトグル
        new_state = not self.params['show_carousel']
        self.params['show_carousel'] = new_state
        self.settings.setValue("show_carousel", new_state)
        
        # 全ウィンドウに適用
        for w in self.windows:
            w.refresh_carousel_visibility()

    def toggle_operation_lock(self):
        self.is_locked = self.act_lock.isChecked()
        for w in self.windows:
            w.set_locked(self.is_locked)

    def open_settings(self):
        self.params['startup'] = is_startup_enabled()
        self.suspend_layers()
        
        dialog = SlideshowSettingsDialog(self.params, self.tr)
        
        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos)
        if not screen: screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        
        target_x = cursor_pos.x() + 10
        target_y = cursor_pos.y() + 10
        d_width = dialog.width()
        d_height = dialog.height()
        
        if target_x + d_width > screen_geo.right():
            target_x = cursor_pos.x() - d_width - 10
        if target_y + d_height > screen_geo.bottom():
            target_y = cursor_pos.y() - d_height - 10
        if target_x < screen_geo.left(): target_x = screen_geo.left()
        if target_y < screen_geo.top(): target_y = screen_geo.top()
        
        dialog.move(target_x, target_y)
        
        if dialog.exec():
            new_params = dialog.get_values()
            if new_params['reset_requested']:
                self.settings.remove("btn_pos")
                self.settings.remove("geometry")
                self.settings.remove("window_states") # Reset saved windows
                self.switch_button.move(100, 100)
                self.act_lock.setChecked(False)
                self.toggle_operation_lock()
            
            if new_params['startup'] != is_startup_enabled():
                set_startup_link(new_params['startup'])

            self.params.update(new_params)
            self.settings.setValue("language", self.params['language'])
            self.settings.setValue("slideshow_interval", self.params['interval'])
            self.settings.setValue("slideshow_active", self.params['active'])
            self.settings.setValue("slideshow_random", self.params['random'])
            self.settings.setValue("fade_duration", self.params['fade'])
            self.settings.setValue("btn_visible", self.params['btn_visible'])
            self.settings.setValue("btn_size", self.params['btn_size'])
            self.settings.setValue("btn_opacity", self.params['btn_opacity'])
            self.settings.setValue("layer_mode", self.params['layer_mode'])
            self.settings.setValue("carousel_pos", self.params['carousel_pos'])
            self.settings.setValue("show_carousel", self.params['show_carousel'])
            self.settings.setValue("anchor_mode", self.params['anchor_mode']) 
            
            self.retranslate_ui()
            self.apply_settings()
        
        self.restore_layers()

    def apply_settings(self):
        ms = self.params['interval'] * 1000
        safe_fade = min(self.params['fade'], max(0, self.params['interval'] - 0.1))
        
        for w in self.windows:
            w.set_slideshow_params(ms, self.params['random'])
            w.set_fade_duration(safe_fade)
            w.set_carousel_position(self.params['carousel_pos'])
            if self.params['active']:
                w.start_slideshow()
            else:
                w.stop_slideshow()
            
            # カルーセルの表示状態も更新
            w.refresh_carousel_visibility()
        
        self.switch_button.set_properties(self.params['btn_size'], self.params['btn_opacity'])
        if self.params['btn_visible']:
            self.switch_button.show()
        else:
            self.switch_button.hide()
        
        self.set_global_layer(self.params['layer_mode'])

    def show_hidden_windows(self):
        if not self.windows:
            self.restore_window_states() # Use restore logic if list empty
            if not self.windows:
                self.create_window()
        else:
            for w in self.windows:
                if not w.isVisible():
                    w.showNormal()
                    w.activateWindow()
                    w.raise_()

    def hide_all_windows(self):
        for w in self.windows:
            w.hide()

    def confirm_close_all_images(self):
        self.suspend_layers()
        
        msg = QMessageBox(QMessageBox.Icon.Question, self.tr('msg_close_title'), self.tr('msg_close_text'),
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        msg.setWindowModality(Qt.WindowModality.ApplicationModal)
        
        if msg.exec() == QMessageBox.StandardButton.Yes:
            self.save_window_states() # Save before closing
            for w in list(self.windows):
                w.force_close()
            self.windows = []
            
            self.settings.remove("window_states")
            
            self.create_window() # Start fresh with one
            
        self.restore_layers()

    def reset_application(self):
        self.suspend_layers()
        
        msg = QMessageBox(QMessageBox.Icon.Question, self.tr('msg_reset_title'), self.tr('msg_reset_text'),
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        msg.setWindowModality(Qt.WindowModality.ApplicationModal)
        
        if msg.exec() == QMessageBox.StandardButton.Yes:
            for w in list(self.windows):
                w.force_close()
            self.windows = []
            
            stack_manager.clear_images()
            self.settings.remove("geometry")
            self.settings.remove("last_index")
            self.settings.remove("btn_pos")
            self.settings.remove("layer_mode")
            self.settings.remove("show_carousel")
            self.settings.remove("window_states") # Clear saved states
            
            self.switch_button.move(100, 100)
            self.set_global_layer('normal')
            self.act_lock.setChecked(False)
            self.toggle_operation_lock()
            
            self.params['language'] = 'ja'
            self.retranslate_ui()
            
            self.create_window()
        
        self.restore_layers()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            any_visible = any(w.isVisible() for w in self.windows)
            if not any_visible:
                self.show_hidden_windows()
            else:
                for w in self.windows:
                    if w.isVisible():
                        w.activateWindow()
                        w.raise_()

    def show_help(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # ★ 言語設定に合わせてファイル名を切り替える
        current_lang = self.params.get('language', 'ja')
        if current_lang == 'en':
            filename = "help_en.txt"
        else:
            filename = "help.txt"
            
        help_path = os.path.join(base_dir, filename)
        
        content = f"Help file ({filename}) not found."
        
        if os.path.exists(help_path):
            try:
                with open(help_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                pass
        
        self.suspend_layers()
        
        dialog = QDialog()
        dialog.setWindowTitle(self.tr('help_title'))
        dialog.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setPlainText(content)
        text_edit.setReadOnly(True)
        layout.addWidget(text_edit)
        dialog.resize(500, 400)
        dialog.exec()
        
        self.restore_layers()

    def save_window_states(self):
        """現在の全ウィンドウの状態を保存"""
        states = []
        for w in self.windows:
            geo = w.geometry()
            state = {
                'rect': [geo.x(), geo.y(), geo.width(), geo.height()],
                'index': w.current_index,
                'offset_x': w.img_offset.x(),
                'offset_y': w.img_offset.y(),
                'scale': w.scale_factor
            }
            states.append(state)
        self.settings.setValue("window_states", json.dumps(states))
        
        if self.windows:
            self.settings.setValue("last_index", self.windows[-1].current_index)
        self.settings.setValue("btn_pos", self.switch_button.pos())

    def restore_window_states(self):
        """保存された状態からウィンドウを復元"""
        json_str = self.settings.value("window_states", "[]")
        try:
            states = json.loads(json_str)
        except Exception:
            states = []

        if states and isinstance(states, list):
            for s in states:
                rect = s.get('rect')
                idx = s.get('index', 0)
                # 安全対策: キーがない場合は None が返る
                off_x = s.get('offset_x')
                off_y = s.get('offset_y')
                scale = s.get('scale')
                
                if rect and len(rect) == 4:
                    win = self.create_window(pos=QPoint(rect[0], rect[1]), size=QSize(rect[2], rect[3]))
                    win.current_index = idx
                    win.update_image_source()
                    
                    # ★ オフセット情報が存在する場合のみ復元
                    if win.pixmap and off_x is not None and off_y is not None and scale is not None:
                        win.scale_factor = scale
                        win.img_offset = QPointF(off_x, off_y)
                        win.update()
        else:
            # データがない場合はデフォルト作成
            self.create_window()

    def close_all(self):
        self.save_window_states() # 終了時に状態保存
        
        for w in list(self.windows):
            w.force_close()
        self.switch_button.close()
        QApplication.quit()

# ---------------------------------------------------------
# UI Components
# ---------------------------------------------------------
class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    scrolled = pyqtSignal(int)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            
    def wheelEvent(self, event):
        self.scrolled.emit(event.angleDelta().y())
    
    # ダブルクリックは無視して親（CarouselWindow）に任せる
    def mouseDoubleClickEvent(self, event):
        event.ignore()

class OverlayButton(QPushButton):
    def __init__(self, text, hint_key, parent_slot):
        super().__init__(text, parent_slot)
        self.hint_key = hint_key
        self.parent_slot = parent_slot
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 150); color: white;
                border: 1px solid rgba(255, 255, 255, 100); border-radius: 4px;
                font-family: Arial; font-size: 10px; padding: 2px 8px;
            }
            QPushButton:hover { background-color: rgba(150, 150, 150, 200); }
        """)

    def enterEvent(self, event):
        if self.parent_slot and self.parent_slot.manager:
            hint = self.parent_slot.manager.tr(self.hint_key)
            self.parent_slot.request_hint(hint)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.parent_slot:
            self.parent_slot.cancel_hint()
        super().leaveEvent(event)

class CustomTooltip(QLabel):
    def __init__(self):
        super().__init__(None)
        # 初期設定はOnTopだが、set_layerで制御される
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet("QLabel { color: white; padding: 5px; font-family: Arial; font-size: 11px; }")
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(0, 0, 0, 128))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 4, 4)
        super().paintEvent(event)

    def show_at(self, global_pos, text):
        self.setText(text)
        self.adjustSize()
        self.move(global_pos + QPoint(15, 15))
        self.show()
        self.raise_() 

# ---------------------------------------------------------
# List View Overlay
# ---------------------------------------------------------
class ListViewOverlay(QWidget):
    image_selected = pyqtSignal(int)
    # 複数選択展開用シグナル: (index, global_rect) のリストを渡す
    images_selected_to_open = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # 常に最前面に固定 (ここが修正ポイント)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        
        self.top_bar = QHBoxLayout()
        self.top_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.top_bar.setSpacing(10)
        
        # --- ボタン類の拡張 ---
        self.btn_select_all = QPushButton("All")
        self.btn_select_all.setFixedSize(40, 20)
        self.btn_select_all.clicked.connect(self.select_all_items)
        
        self.btn_open = QPushButton("Open")
        self.btn_open.setFixedSize(50, 20)
        self.btn_open.clicked.connect(self.open_selected)

        self.btn_minus = QPushButton("－")
        self.btn_minus.setFixedSize(40, 20)
        self.btn_plus = QPushButton("＋")
        self.btn_plus.setFixedSize(40, 20)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(50, 600)
        self.slider.setValue(150)
        self.slider.setFixedWidth(150)
        
        # Closeボタンの追加
        self.btn_close = QPushButton("✕ Close")
        self.btn_close.setFixedSize(60, 20)
        self.btn_close.clicked.connect(self.hide)
        
        ctrl_style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 30); color: white;
                border: 1px solid rgba(255, 255, 255, 100); border-radius: 10px; font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 80); }
            QSlider::groove:horizontal { height: 4px; background: #555; border-radius: 2px; }
            QSlider::handle:horizontal { background: white; width: 14px; margin: -5px 0; border-radius: 7px; }
        """
        self.btn_select_all.setStyleSheet(ctrl_style)
        self.btn_open.setStyleSheet(ctrl_style)
        self.btn_minus.setStyleSheet(ctrl_style)
        self.btn_plus.setStyleSheet(ctrl_style)
        self.slider.setStyleSheet(ctrl_style)
        self.btn_close.setStyleSheet(ctrl_style)
        
        self.top_bar.addWidget(self.btn_select_all)
        self.top_bar.addWidget(self.btn_open)
        self.top_bar.addSpacing(10)
        self.top_bar.addWidget(self.btn_minus)
        self.top_bar.addWidget(self.slider)
        self.top_bar.addWidget(self.btn_plus)
        self.top_bar.addSpacing(10)
        self.top_bar.addWidget(self.btn_close)
        self.layout.addLayout(self.top_bar)
        
        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setSpacing(10) # ★ Spacingを10に変更
        self.list_widget.setIconSize(QSize(150, 150))
        self.list_widget.setMovement(QListWidget.Movement.Static)
        
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.setSelectionRectVisible(True) # ドラッグ範囲選択を有効化
        
        # ★ マージンを5px確保して隙間を作る
        self.list_widget.setStyleSheet("""
            QListWidget { 
                background-color: transparent; 
                border: none; 
                outline: none; 
                font-size: 0px; 
            }
            QListWidget::item { color: white; margin: 5px; }
            QListWidget::item:selected { background-color: rgba(255, 255, 255, 50); border-radius: 5px; }
            QScrollBar:vertical { border: none; background: rgba(255,255,255,20); width: 10px; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,100); min-height: 20px; border-radius: 5px; }
        """)
        self.layout.addWidget(self.list_widget)
        
        self.slider.valueChanged.connect(self.update_icon_size)
        self.btn_minus.clicked.connect(lambda: self.slider.setValue(self.slider.value() - 50))
        self.btn_plus.clicked.connect(lambda: self.slider.setValue(self.slider.value() + 50))
        
        self.list_widget.itemActivated.connect(self.on_item_clicked)
        self.list_widget.viewport().installEventFilter(self)
        stack_manager.thumbnail_updated.connect(self.update_single_thumbnail)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(0, 0, 0, 245))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(self.rect())

    def load_images(self):
        self.list_widget.clear()
        for i, path in enumerate(stack_manager.image_paths):
            icon = stack_manager.get_icon(path, for_list=True)
            item = QListWidgetItem(icon, "")
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setData(Qt.ItemDataRole.UserRole + 1, path) 
            self.list_widget.addItem(item)

    def update_single_thumbnail(self, path):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole + 1) == path:
                icon = stack_manager.get_icon(path, for_list=True)
                item.setIcon(icon)
                return

    def update_icon_size(self, val):
        self.list_widget.setIconSize(QSize(val, val))

    def on_item_clicked(self, item):
        idx = item.data(Qt.ItemDataRole.UserRole)
        self.image_selected.emit(idx)
        self.hide()

    def select_all_items(self):
        self.list_widget.selectAll()

    def open_selected(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items: return
        
        items_to_open = []
        for item in selected_items:
            idx = item.data(Qt.ItemDataRole.UserRole)
            rect = self.list_widget.visualItemRect(item)
            global_pos = self.list_widget.viewport().mapToGlobal(rect.topLeft())
            global_rect = QRect(global_pos, rect.size())
            items_to_open.append((idx, global_rect))
        
        self.images_selected_to_open.emit(items_to_open)
        self.hide()

    def eventFilter(self, source, event):
        if source == self.list_widget.viewport():
            if event.type() == event.Type.MouseButtonDblClick:
                # ログ削除済: 何もないところをダブルクリックしたら閉じる
                if not self.list_widget.itemAt(event.pos()):
                    self.hide()
                    return True
        return super().eventFilter(source, event)

    def show_fullscreen(self):
        self.setGeometry(QApplication.primaryScreen().geometry())
        self.load_images()
        self.show()
        self.raise_()

# ---------------------------------------------------------
# Carousel Window
# ---------------------------------------------------------
class CarouselWindow(QWidget):
    def __init__(self, parent_slot):
        super().__init__(parent_slot)
        self.parent_slot = parent_slot
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(0.0)
        
        self.thumb_h = 50
        self.thumb_w = 75 
        self.spacing = 5
        self.margin_from_frame = 15
        self.unit_width = self.thumb_w + self.spacing
        self.buffer_count = 5 
        self.position_mode = 'top'
        self.fixed_height = 54

        self.setStyleSheet(f".CarouselWindow {{ background-color: rgba(0, 0, 0, 180); border-radius: 5px; }}")

        self.container = QWidget(self)
        self.container_layout = QHBoxLayout()
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(self.spacing)
        self.container.setLayout(self.container_layout)
        
        self.labels = []
        # 分離された選択枠
        self.selection_bg = QLabel(self)
        self.selection_bg.setFixedSize(self.thumb_w + 4, self.thumb_h + 4)
        self.selection_bg.setStyleSheet("background-color: rgba(0, 0, 0, 128); border: none;")
        self.selection_bg.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.selection_border = QLabel(self)
        self.selection_border.setFixedSize(self.thumb_w + 4, self.thumb_h + 4)
        self.selection_border.setStyleSheet("border: 2px solid white; background-color: transparent;")
        self.selection_border.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        nav_btn_style = """
            QPushButton {
                background-color: rgba(0, 0, 0, 150); color: white;
                border: 1px solid rgba(255, 255, 255, 100);
                border-radius: 12px; font-family: Arial; font-weight: bold; font-size: 14px; padding-bottom: 2px;
            }
            QPushButton:hover { background-color: rgba(150, 150, 150, 200); border-color: white; }
        """
        self.btn_prev = QPushButton("<", self)
        self.btn_prev.setFixedSize(24, 24)
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev.setStyleSheet(nav_btn_style)
        self.btn_prev.clicked.connect(lambda: self.parent_slot.change_image(-1))

        self.btn_next = QPushButton(">", self)
        self.btn_next.setFixedSize(24, 24)
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.setStyleSheet(nav_btn_style)
        self.btn_next.clicked.connect(lambda: self.parent_slot.change_image(1))

        self.anim_slide = QPropertyAnimation(self.container, b"pos")
        self.anim_slide.setDuration(200)
        self.anim_slide.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.anim_slide.finished.connect(self.on_slide_finished)
        
        self.ideal_width = 0   
        self.base_x = 0        
        self.logical_base_x = 0 
        self.current_visible_count = 0
        self.hide()

    def set_position_mode(self, mode):
        self.position_mode = mode
        self.update_position()

    def calculate_visible_count(self):
        if not stack_manager.image_paths: return 0
        return max(1, min(len(stack_manager.image_paths), 24))

    def update_content(self):
        paths = stack_manager.image_paths
        if not paths: 
            self.hide()
            return

        self.current_visible_count = self.calculate_visible_count()
        self.ideal_width = (self.unit_width * self.current_visible_count) + self.spacing
        
        self.resize(self.ideal_width, self.fixed_height)

        needed_slots = self.current_visible_count + (self.buffer_count * 2)
        self.clear_container()
        self.labels = []
        
        container_w = (self.unit_width * needed_slots) 
        self.container.resize(container_w, self.thumb_h) 
        self.container.setFixedHeight(self.thumb_h)
        
        self.logical_base_x = self.spacing - (self.buffer_count * self.unit_width)
        self.base_x = self.logical_base_x
        self.container.move(self.base_x, 2)

        target_visual_index = (self.current_visible_count - 1) // 2
        center_slot_idx = self.buffer_count + target_visual_index
        
        for i in range(needed_slots):
            lbl = ClickableLabel()
            lbl.setFixedSize(self.thumb_w, self.thumb_h)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("background-color: transparent;")
            lbl.scrolled.connect(self.handle_child_scroll)
            
            offset = i - center_slot_idx
            lbl.clicked.connect(lambda o=offset: self.parent_slot.change_image(o))
            self.container_layout.addWidget(lbl)
            self.labels.append(lbl)

        self.refresh_thumbnails()
        self.update_position()
        
        # Zオーダー調整: 背景 < コンテナ < ボーダー < ボタン
        self.selection_bg.lower()
        self.container.stackUnder(self.selection_border) # コンテナはボーダーの下
        self.selection_border.raise_()
        self.btn_prev.raise_()
        self.btn_next.raise_()

    def handle_child_scroll(self, angle):
        if angle > 0:
            self.parent_slot.change_image(-1)
        else:
            self.parent_slot.change_image(1)

    def refresh_thumbnails(self):
        paths = stack_manager.image_paths
        if not paths: return
        total_imgs = len(paths)
        current_idx = self.parent_slot.current_index % total_imgs
        
        target_visual_index = (self.current_visible_count - 1) // 2
        center_slot_idx = self.buffer_count + target_visual_index
        start_offset = -center_slot_idx
        
        for i, lbl in enumerate(self.labels):
            offset = start_offset + i
            img_idx = (current_idx + offset) % total_imgs
            path = paths[img_idx]
            icon = stack_manager.get_icon(path, for_list=False)
            if not icon.isNull():
                pix = icon.pixmap(self.thumb_w, self.thumb_h)
                lbl.setPixmap(pix)

    def clear_container(self):
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def update_position(self):
        if not self.parent_slot.isVisible() or not stack_manager.image_paths:
            self.hide()
            return
        
        parent_w = self.parent_slot.width()
        
        # カルーセル幅を親に合わせる (最大化)
        final_w = parent_w 
        self.resize(final_w, self.height())
        
        # 中央寄せ配置のためのオフセット計算
        center_x = (final_w - self.thumb_w) // 2
        
        # 枠と背景を中央に配置
        self.selection_bg.move(center_x - 2, 0) # -2px for visual centering
        self.selection_border.move(center_x - 2, 0)
        
        # コンテナの配置
        active_item_index_in_container = self.buffer_count + (self.current_visible_count - 1) // 2
        # ★ 修正: spacingを加算しない
        active_item_x_in_container = (active_item_index_in_container * self.unit_width)
        
        self.base_x = center_x - active_item_x_in_container
        
        if self.anim_slide.state() != QAbstractAnimation.State.Running:
            self.container.move(self.base_x, 2)

        btn_y = (self.height() - self.btn_prev.height()) // 2
        self.btn_prev.move(2, btn_y)
        self.btn_next.move(self.width() - self.btn_next.width() - 2, btn_y)
        self.btn_prev.raise_()
        self.btn_next.raise_()

        parent_geo = self.parent_slot.frameGeometry()
        
        # カルーセル自体の位置 (親の下/上)
        global_top_left = self.parent_slot.mapToGlobal(QPoint(0, 0))
        target_global_x = global_top_left.x()
        
        if self.position_mode == 'top':
            target_global_y = global_top_left.y() - self.height() - self.margin_from_frame
        else:
            target_global_y = global_top_left.y() + self.parent_slot.height() + self.margin_from_frame
            
        self.move(target_global_x, target_global_y)

    def slide(self, direction):
        if self.anim_slide.state() == QAbstractAnimation.State.Running: return
        target_x = self.base_x - (direction * self.unit_width)
        self.anim_slide.setStartValue(self.container.pos())
        self.anim_slide.setEndValue(QPoint(target_x, self.container.y()))
        self.anim_slide.start()

    def on_slide_finished(self):
        self.container.move(self.base_x, self.container.y())
        self.refresh_thumbnails()

    def wheelEvent(self, event):
        angle = event.angleDelta().y()
        if angle > 0: self.parent_slot.change_image(-1) 
        else: self.parent_slot.change_image(1)

    # ★ 追加: 右クリックメニューとダブルクリック判定
    def contextMenuEvent(self, event):
        if self.manager.is_locked: return
        if self.suppress_context_menu:
            self.suppress_context_menu = False
            return
        menu = QMenu(self)
        
        # Translate context menu
        add_text = "スロットを追加"
        move_text = "モニター外の表示を戻す"
        list_text = "一覧リストを表示"
        toggle_text = "サムネイルの表示/非表示"
        
        if self.manager:
            add_text = self.manager.tr('slot_add')
            move_text = self.manager.tr('slot_move_back')
            list_text = self.manager.tr('menu_view_list')
            toggle_text = self.manager.tr('menu_toggle_carousel')

        add_slot_action = QAction(add_text, self)
        add_slot_action.triggered.connect(self.add_new_slot)
        menu.addAction(add_slot_action)
        
        move_screen_action = QAction(move_text, self)
        move_screen_action.triggered.connect(self.move_inside_screen)
        menu.addAction(move_screen_action)
        
        menu.addSeparator()

        action_list = QAction(list_text, self)
        action_list.triggered.connect(self.action_list)
        menu.addAction(action_list)
        
        action_toggle = QAction(toggle_text, self)
        action_toggle.setCheckable(True)
        if self.manager:
            action_toggle.setChecked(self.manager.params['show_carousel'])
            action_toggle.triggered.connect(self.manager.toggle_global_carousel)
        menu.addAction(action_toggle)
        
        menu.exec(event.globalPos())

    def mouseDoubleClickEvent(self, event):
        # 白枠（選択中画像）の中ならリスト表示
        if self.selection_border.geometry().contains(event.pos()):
            self.parent_slot.action_list()

# ---------------------------------------------------------
# Main Image Slot
# ---------------------------------------------------------
class ImageSlot(QWidget):
    def __init__(self, image_index=0, manager=None):
        super().__init__()
        self.manager = manager
        self.current_index = image_index
        self.pixmap = None
        self.scale_factor = 1.0
        
        # ★ 追加: 画像のオフセット管理変数
        self.img_offset = QPointF(0.0, 0.0)
        self.start_img_offset = QPointF(0.0, 0.0)
        
        self.old_pixmap = None
        self.old_scale_factor = 1.0  # ★ フェード時のサイズズレ防止用
        self.transition_progress = 0.0
        
        self.is_ui_visible = False
        self.border_opacity = 0.0
        self.drag_pos = None
        self.resizing = False
        self.resize_edge = None 
        self.resize_button = None
        self.suppress_context_menu = False
        self.border_margin = 10
        self.slideshow_random = False 
        
        self.setMinimumSize(50, 50) # 緩和
        self.settings = QSettings("Tokitoma", "FloatRef")

        if self.manager:
            self.setWindowIcon(self.manager.app_icon)
        else:
            self.setWindowIcon(self.create_gray_icon())

        self.initUI()
        self.tooltip_window = CustomTooltip()

        self.carousel = CarouselWindow(self)
        pos_mode = self.settings.value("carousel_pos", "top")
        self.carousel.set_position_mode(pos_mode)

        self.list_overlay = ListViewOverlay()
        self.list_overlay.image_selected.connect(self.jump_to_image)
        self.list_overlay.images_selected_to_open.connect(self.request_open_multiple)

        self.btn_fit = OverlayButton("Fit", "btn_fit_hint", self)
        self.btn_fit.clicked.connect(self.action_fit)
        
        self.btn_trim = OverlayButton("Trim", "btn_trim_hint", self)
        self.btn_trim.clicked.connect(self.action_trim)
        
        self.btn_list = OverlayButton("List", "btn_list_hint", self)
        self.btn_list.clicked.connect(self.action_list)
        
        # 最小化ボタン
        self.btn_min = QPushButton("－", self)
        self.btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_min.setFixedSize(24, 24)
        btn_style = """
            QPushButton {
                background-color: rgba(0, 0, 0, 150); color: white;
                border: 1px solid rgba(255, 255, 255, 100);
                border-radius: 12px; font-family: Arial; font-weight: bold; font-size: 10px; padding-bottom: 2px;
            }
            QPushButton:hover { background-color: rgba(150, 150, 150, 200); border-color: white; }
        """
        self.btn_min.setStyleSheet(btn_style)
        self.btn_min.clicked.connect(self.hide)

        # 閉じるボタン
        self.btn_close = QPushButton("✕", self)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setStyleSheet(btn_style)
        self.btn_close.clicked.connect(self.close)
        
        self.eff_fit = QGraphicsOpacityEffect(self.btn_fit)
        self.eff_trim = QGraphicsOpacityEffect(self.btn_trim)
        self.eff_list = QGraphicsOpacityEffect(self.btn_list)
        self.eff_min = QGraphicsOpacityEffect(self.btn_min)
        self.eff_close = QGraphicsOpacityEffect(self.btn_close)
        
        self.eff_fit.setOpacity(0.0)
        self.eff_trim.setOpacity(0.0)
        self.eff_list.setOpacity(0.0)
        self.eff_min.setOpacity(0.0)
        self.eff_close.setOpacity(0.0)
        
        self.btn_fit.setGraphicsEffect(self.eff_fit)
        self.btn_trim.setGraphicsEffect(self.eff_trim)
        self.btn_list.setGraphicsEffect(self.eff_list)
        self.btn_min.setGraphicsEffect(self.eff_min)
        self.btn_close.setGraphicsEffect(self.eff_close)
        
        self.btn_fit.hide()
        self.btn_trim.hide()
        self.btn_list.hide()
        self.btn_min.hide()
        self.btn_close.hide()

        self.hint_timer = QTimer(self)
        self.hint_timer.setSingleShot(True)
        self.hint_timer.setInterval(1000) 
        self.hint_timer.timeout.connect(self.show_pending_hint)
        self.pending_hint_text = ""

        self.show_delay_timer = QTimer(self)
        self.show_delay_timer.setSingleShot(True)
        self.show_delay_timer.setInterval(200) 
        self.show_delay_timer.timeout.connect(self.fade_in_ui)

        self.hover_check_timer = QTimer(self)
        self.hover_check_timer.setInterval(50) 
        self.hover_check_timer.timeout.connect(self.check_hover_state)
        
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(700)
        self.hide_timer.timeout.connect(self.fade_out_ui)

        self.slide_timer = QTimer(self)
        self.slide_timer.setInterval(10000) 
        self.slide_timer.timeout.connect(lambda: self.handle_slideshow_tick())

        self.anim_group = QParallelAnimationGroup()
        self.setup_animations()
        
        self.fade_anim = QVariantAnimation()
        self.fade_anim.setDuration(200) 
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.valueChanged.connect(self.update_fade_progress)
        self.fade_anim.finished.connect(self.on_fade_finished_img)

    def refresh_carousel_visibility(self):
        """カルーセルの表示設定が変更されたときに呼ばれる"""
        if self.manager.params['show_carousel'] and self.is_ui_visible:
            if self.carousel.anim_slide.state() != QAbstractAnimation.State.Running:
                self.carousel.update_content()
                self.carousel.update_position()
            self.carousel.show()
            self.anim_carousel.setEndValue(1.0) # アニメーションターゲットも更新
            self.carousel.setWindowOpacity(1.0)
        else:
            self.carousel.hide()
            self.anim_carousel.setEndValue(0.0)

    def jump_to_image(self, index):
        if not stack_manager.image_paths: return
        self.current_index = index
        self.update_image_source() # or refresh_content_keep_frame

    def update_text(self):
        pass

    def request_open_multiple(self, items):
        if self.manager:
            self.manager.open_multiple_windows(items)

    def create_gray_icon(self):
        pix = QPixmap(64, 64)
        pix.fill(QColor(100, 100, 100))
        return QIcon(pix)

    def initUI(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        if self.settings.value("geometry"):
            self.restoreGeometry(self.settings.value("geometry"))
        else:
            self.resize(300, 300)

    def set_fade_duration(self, duration_sec):
        self.fade_anim.setDuration(int(duration_sec * 1000))

    def set_carousel_position(self, mode):
        self.carousel.set_position_mode(mode)

    def set_layer_mode(self, mode):
        flags = Qt.WindowType.FramelessWindowHint
        if mode == 'top':
            flags |= Qt.WindowType.WindowStaysOnTopHint
        elif mode == 'bottom':
            flags |= Qt.WindowType.WindowStaysOnBottomHint
        
        was_visible = self.isVisible()
        self.hide()
        self.setWindowFlags(flags)
        
        sub_flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if mode == 'top':
            sub_flags |= Qt.WindowType.WindowStaysOnTopHint
        elif mode == 'bottom':
            sub_flags |= Qt.WindowType.WindowStaysOnBottomHint
            
        self.carousel.setWindowFlags(sub_flags)
        # リストだけは常に最前面にするフラグを設定
        list_flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
        self.list_overlay.setWindowFlags(list_flags)
        
        tooltip_flags = Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
        if mode == 'top':
            tooltip_flags |= Qt.WindowType.WindowStaysOnTopHint
        elif mode == 'bottom':
            tooltip_flags |= Qt.WindowType.WindowStaysOnBottomHint
        self.tooltip_window.setWindowFlags(tooltip_flags)

        if was_visible:
            self.show()

    def set_locked(self, locked):
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, locked)
        if locked:
            self.is_ui_visible = False
            self.carousel.hide()
            self.btn_fit.hide()
            self.btn_trim.hide()
            self.btn_list.hide()
            self.btn_min.hide()
            self.btn_close.hide()
            self.tooltip_window.hide()
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def force_close(self):
        self.tooltip_window.close()
        self.list_overlay.close()
        self.carousel.close()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        super().close()

    def closeEvent(self, event):
        # 個別ウィンドウでの geometry 保存は廃止（一括保存に移行）
        self.tooltip_window.hide()
        self.list_overlay.hide()
        self.carousel.hide()
        self.manager.on_window_closed(self) 
        event.accept()

    def leaveEvent(self, event):
        self.cancel_hint()
        super().leaveEvent(event)

    def request_hint(self, text):
        self.pending_hint_text = text
        self.hint_timer.start()

    def cancel_hint(self):
        self.hint_timer.stop()
        self.tooltip_window.hide()

    def show_pending_hint(self):
        current_pos = QCursor.pos()
        window_rect = self.frameGeometry()
        if not window_rect.adjusted(-20, -20, 20, 20).contains(current_pos):
            return 
        if self.pending_hint_text:
            self.tooltip_window.show_at(current_pos, self.pending_hint_text)

    def mousePressEvent(self, event):
        if self.manager.is_locked: return
        self.cancel_hint()
        # ★ 追加: クリック時にもスイッチボタンを手前に
        if self.manager:
            self.manager.bring_switch_to_front()
            
        if self.resize_edge:
            if event.button() == Qt.MouseButton.LeftButton:
                # ★ 左クリック: Fitしてからリサイズ開始
                self.action_fit() # 一旦Fitさせる
                self.resizing = True
                self.resize_button = event.button()
                self.drag_pos = event.globalPosition().toPoint()
                self.start_geometry = self.geometry()
                self.suppress_context_menu = True
                return
            elif event.button() == Qt.MouseButton.RightButton:
                # ★ 右クリック: 枠のみリサイズ (開始時にオフセットを保存)
                self.resizing = True
                self.resize_button = event.button()
                self.drag_pos = event.globalPosition().toPoint()
                self.start_geometry = self.geometry()
                self.start_img_offset = QPointF(self.img_offset) # 現在のオフセットを保存
                self.suppress_context_menu = True
                return

        if event.button() == Qt.MouseButton.RightButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.suppress_context_menu = False
        elif event.button() == Qt.MouseButton.MiddleButton:
             # ★ 中クリック: パン開始
             self.drag_pos = event.globalPosition().toPoint()
             self.suppress_context_menu = True

    def mouseMoveEvent(self, event):
        if self.manager.is_locked: return
        
        # ★ 追加: ダイアログ表示中はホバー反応を無効化
        if QApplication.activeModalWidget(): 
            if self.is_ui_visible:
                self.hide_timer.start(0) 
            return

        # ★ 追加: マウス移動中もスイッチボタンを手前に（重くなる場合はここを削除してもOK）
        if self.manager:
            self.manager.bring_switch_to_front()

        if self.resizing:
            self.handle_resize(event)
            self.update_satellites()
            return
        
        # 右ドラッグ（ウィンドウ移動）
        if event.buttons() & Qt.MouseButton.RightButton and self.drag_pos:
            move_vector = (event.globalPosition().toPoint() - self.drag_pos) - self.frameGeometry().topLeft()
            if move_vector.manhattanLength() > 5:
                self.suppress_context_menu = True
                self.move(event.globalPosition().toPoint() - self.drag_pos)
                self.update_satellites()
            return

        # ★ 中ドラッグ（画像パン）
        if event.buttons() & Qt.MouseButton.MiddleButton and self.drag_pos:
            curr_pos = event.globalPosition().toPoint()
            diff = curr_pos - self.drag_pos
            self.drag_pos = curr_pos
            
            # オフセットを加算
            self.img_offset += QPointF(diff)
            self.update()
            return

        if self.pixmap is not None:
            self.update_cursor(event.pos())
        if not self.hover_check_timer.isActive():
             self.hover_check_timer.start()

    def mouseReleaseEvent(self, event):
        self.resizing = False
        self.drag_pos = None

    def update_cursor(self, pos):
        child = self.childAt(pos)
        if child:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if not isinstance(child, OverlayButton):
                self.cancel_hint()
            return

        m = self.border_margin
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()
        self.resize_edge = None
        
        if x < m and y < m: self.resize_edge = 'top-left'
        elif x > w-m and y < m: self.resize_edge = 'top-right'
        elif x < m and y > h-m: self.resize_edge = 'bottom-left'
        elif x > w-m and y > h-m: self.resize_edge = 'bottom-right'
        elif x < m: self.resize_edge = 'left'
        elif x > w-m: self.resize_edge = 'right'
        elif y < m: self.resize_edge = 'top'
        elif y > h-m: self.resize_edge = 'bottom'
        
        cursors = {
            'top-left': Qt.CursorShape.SizeFDiagCursor, 
            'bottom-right': Qt.CursorShape.SizeFDiagCursor, 
            'top-right': Qt.CursorShape.SizeBDiagCursor, 
            'bottom-left': Qt.CursorShape.SizeBDiagCursor, 
            'left': Qt.CursorShape.SizeHorCursor, 
            'right': Qt.CursorShape.SizeHorCursor, 
            'top': Qt.CursorShape.SizeVerCursor, 
            'bottom': Qt.CursorShape.SizeVerCursor
        }
        
        if self.resize_edge: 
            self.setCursor(cursors[self.resize_edge])
            if not self.tooltip_window.isVisible() and not self.hint_timer.isActive():
                if self.manager:
                    self.pending_hint_text = self.manager.tr('resize_hint')
                else:
                    self.pending_hint_text = "Resize"
                self.hint_timer.start()
        else: 
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.cancel_hint()

    def wheelEvent(self, event):
        if self.manager.is_locked: return # ★ 追加: ロック中はズーム無効
        
        if self.pixmap is None: return
        
        # ★ ホイール: カーソル位置中心ズーム
        # 現在のカーソル位置（ウィンドウ内座標）
        cursor_pos = event.position()
        
        # カーソル位置における「画像内の相対座標」を逆算
        rel_vec = cursor_pos - self.img_offset
        
        angle = event.angleDelta().y()
        zoom_factor = 1.1 if angle > 0 else 1/1.1
        
        new_scale = self.scale_factor * zoom_factor
        
        # 新しいオフセットを計算
        new_offset = cursor_pos - (rel_vec * zoom_factor)
        
        self.scale_factor = new_scale
        self.img_offset = new_offset
        
        self.update()

    def action_fit(self):
        if self.pixmap is None: return
        self.calculate_fit_scale()
        self.update() 

    def action_trim(self):
        if self.pixmap is None: return
        self.resize_window_to_image_size() 

    def action_list(self):
        if not stack_manager.image_paths: return
        self.list_overlay.show_fullscreen()

    def resize_window_to_image_size(self):
        target_w = int(self.pixmap.width() * self.scale_factor) + 4
        target_h = int(self.pixmap.height() * self.scale_factor) + 4
        
        # 中心維持でリサイズ
        current_geo = self.geometry()
        center = current_geo.center()
        new_x = center.x() - (target_w // 2)
        new_y = center.y() - (target_h // 2)
        
        # 画面内チェック
        screen_geo = self.screen().availableGeometry()
        if target_w > screen_geo.width(): target_w = screen_geo.width()
        if target_h > screen_geo.height(): target_h = screen_geo.height()
        
        self.setGeometry(new_x, new_y, target_w, target_h)
        
        # Trimした時点でFit（中央）状態にする
        self.calculate_fit_scale()
        
        self.update_satellites()

    def update_satellites(self):
        self.update()
        if self.carousel.isVisible(): self.carousel.update_position()
        self.position_buttons()

    def move_inside_screen(self):
        screen = self.screen().availableGeometry()
        geo = self.frameGeometry()
        should_resize = False
        new_w = geo.width()
        new_h = geo.height()
        if new_w > screen.width():
            new_w = screen.width()
            should_resize = True
        if new_h > screen.height():
            new_h = screen.height()
            should_resize = True
        if should_resize:
            if self.pixmap:
                self.scale_factor = min((new_w - 4) / self.pixmap.width(), (new_h - 4) / self.pixmap.height())
                # リサイズ時はFitさせる
                self.calculate_fit_scale()

            self.resize(new_w, new_h)
            geo = self.frameGeometry()
            
        new_x, new_y = geo.x(), geo.y()
        if geo.right() > screen.right(): new_x = screen.right() - geo.width()
        if new_x < screen.left(): new_x = screen.left()
        if geo.bottom() > screen.bottom(): new_y = screen.bottom() - geo.height()
        if new_y < screen.top(): new_y = screen.top()
        if new_x != geo.x() or new_y != geo.y():
            self.move(new_x, new_y)
            self.update_satellites()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.move_inside_screen()

    def resizeEvent(self, event):
        self.update_satellites()
        super().resizeEvent(event)

    # ★ 追加: 右クリックメニューとダブルクリック判定
    def contextMenuEvent(self, event):
        if self.manager.is_locked: return
        if self.suppress_context_menu:
            self.suppress_context_menu = False
            return
        menu = QMenu(self)
        
        # Translate context menu
        add_text = "スロットを追加"
        move_text = "モニター外の表示を戻す"
        list_text = "一覧リストを表示"
        toggle_text = "サムネイルの表示/非表示"
        btn_vis_text = "スイッチボタンを表示" # Default
        
        if self.manager:
            add_text = self.manager.tr('slot_add')
            move_text = self.manager.tr('slot_move_back')
            list_text = self.manager.tr('menu_view_list')
            toggle_text = self.manager.tr('menu_toggle_carousel')
            btn_vis_text = self.manager.tr('menu_show_switch_btn')

        add_slot_action = QAction(add_text, self)
        add_slot_action.triggered.connect(self.add_new_slot)
        menu.addAction(add_slot_action)
        
        move_screen_action = QAction(move_text, self)
        move_screen_action.triggered.connect(self.move_inside_screen)
        menu.addAction(move_screen_action)
        
        menu.addSeparator()

        action_list = QAction(list_text, self)
        action_list.triggered.connect(self.action_list)
        menu.addAction(action_list)
        
        action_toggle = QAction(toggle_text, self)
        action_toggle.setCheckable(True)
        if self.manager:
            action_toggle.setChecked(self.manager.params['show_carousel'])
            action_toggle.triggered.connect(self.manager.toggle_global_carousel)
        menu.addAction(action_toggle)
        
        # ★ スイッチボタン表示切替を追加
        action_btn_vis = QAction(btn_vis_text, self)
        action_btn_vis.setCheckable(True)
        if self.manager:
            action_btn_vis.setChecked(self.manager.params['btn_visible'])
            action_btn_vis.triggered.connect(self.toggle_switch_btn_visible)
        menu.addAction(action_btn_vis)
        
        menu.exec(event.globalPos())

    def toggle_switch_btn_visible(self, checked):
        if self.manager:
            self.manager.params['btn_visible'] = checked
            self.manager.settings.setValue("btn_visible", checked)
            self.manager.apply_settings()

    def add_new_slot(self):
        if self.manager:
            new_pos = self.pos() + QPoint(20, 20)
            new_win = self.manager.create_window(new_pos, next_image=True)

    def setup_animations(self):
        self.anim_group = QParallelAnimationGroup()
        self.anim_carousel = QPropertyAnimation(self.carousel, b"windowOpacity")
        self.anim_carousel.setDuration(100)
        self.anim_group.addAnimation(self.anim_carousel)
        self.anim_fit = QPropertyAnimation(self.eff_fit, b"opacity")
        self.anim_fit.setDuration(100)
        self.anim_group.addAnimation(self.anim_fit)
        self.anim_trim = QPropertyAnimation(self.eff_trim, b"opacity")
        self.anim_trim.setDuration(100)
        self.anim_group.addAnimation(self.anim_trim)
        self.anim_list = QPropertyAnimation(self.eff_list, b"opacity")
        self.anim_list.setDuration(100)
        self.anim_group.addAnimation(self.anim_list)
        self.anim_min = QPropertyAnimation(self.eff_min, b"opacity")
        self.anim_min.setDuration(100)
        self.anim_group.addAnimation(self.anim_min)
        self.anim_close = QPropertyAnimation(self.eff_close, b"opacity")
        self.anim_close.setDuration(100)
        self.anim_group.addAnimation(self.anim_close)
        self.anim_border = QVariantAnimation()
        self.anim_border.setDuration(100)
        self.anim_border.valueChanged.connect(self.update_border_opacity)
        self.anim_group.addAnimation(self.anim_border)
        self.anim_group.finished.connect(self.on_fade_finished)

    def update_border_opacity(self, value):
        self.border_opacity = value
        self.update()

    def fade_in_ui(self):
        # ロック中はUIを出さない
        if self.manager.is_locked: return
        
        # ★ 追加: リスト表示中はホバー判定を無効化
        if self.list_overlay.isVisible():
            if self.is_ui_visible:
                self.hide_timer.start(0) # 即座に隠す
            return

        self.hide_timer.stop()
        if self.is_ui_visible: return
        self.is_ui_visible = True
        if self.pixmap:
            # カルーセル表示設定を確認
            if self.manager.params['show_carousel']:
                self.carousel.show()
                self.carousel.update_content()
                self.carousel.update_position()
            else:
                self.carousel.hide()
            
            self.btn_fit.show()
            self.btn_trim.show()
            self.btn_list.show()
            self.btn_min.show()
            self.btn_close.show()
            self.position_buttons()
        self.anim_group.stop()
        self.anim_carousel.setEndValue(1.0)
        self.anim_fit.setEndValue(1.0)
        self.anim_trim.setEndValue(1.0)
        self.anim_list.setEndValue(1.0)
        self.anim_min.setEndValue(1.0)
        self.anim_close.setEndValue(1.0)
        self.anim_border.setEndValue(1.0)
        self.anim_carousel.setStartValue(self.carousel.windowOpacity())
        self.anim_fit.setStartValue(self.eff_fit.opacity())
        self.anim_trim.setStartValue(self.eff_trim.opacity())
        self.anim_list.setStartValue(self.eff_list.opacity())
        self.anim_min.setStartValue(self.eff_min.opacity())
        self.anim_close.setStartValue(self.eff_close.opacity())
        self.anim_border.setStartValue(self.border_opacity)
        self.anim_group.start()

    def fade_out_ui(self):
        self.anim_group.stop()
        self.anim_carousel.setEndValue(0.0)
        self.anim_fit.setEndValue(0.0)
        self.anim_trim.setEndValue(0.0)
        self.anim_list.setEndValue(0.0)
        self.anim_min.setEndValue(0.0)
        self.anim_close.setEndValue(0.0)
        self.anim_border.setEndValue(0.0)
        self.anim_carousel.setStartValue(self.carousel.windowOpacity())
        self.anim_fit.setStartValue(self.eff_fit.opacity())
        self.anim_trim.setStartValue(self.eff_trim.opacity())
        self.anim_list.setStartValue(self.eff_list.opacity())
        self.anim_min.setStartValue(self.eff_min.opacity())
        self.anim_close.setStartValue(self.eff_close.opacity())
        self.anim_border.setStartValue(self.border_opacity)
        self.anim_group.start()

    def on_fade_finished(self):
        if self.border_opacity == 0.0:
            self.is_ui_visible = False
            self.carousel.hide()
            self.btn_fit.hide()
            self.btn_trim.hide()
            self.btn_list.hide()
            self.btn_min.hide()
            self.btn_close.hide()

    def position_buttons(self):
        m = 10
        gap = 5
        self.btn_fit.move(m, m)
        self.btn_trim.move(self.btn_fit.geometry().right() + gap, m)
        self.btn_list.move(self.btn_trim.geometry().right() + gap, m)
        self.btn_close.move(self.width() - self.btn_close.width() - 15, 15)
        self.btn_min.move(self.btn_close.geometry().left() - self.btn_min.width() - 5, 15)

    def set_on_top(self, on_top):
        # 互換性のため残すが、基本はset_layer_modeを使う
        mode = 'top' if on_top else 'bottom'
        self.set_layer_mode(mode)

    def set_slideshow_params(self, ms, random_mode):
        self.slide_timer.setInterval(ms)
        self.slideshow_random = random_mode
        if self.slide_timer.isActive():
            self.slide_timer.start()

    def start_slideshow(self):
        if not self.slide_timer.isActive() and stack_manager.image_paths:
            self.slide_timer.start()

    def stop_slideshow(self):
        self.slide_timer.stop()

    def handle_slideshow_tick(self):
        if not stack_manager.image_paths: return
        if self.slideshow_random and len(stack_manager.image_paths) > 1:
            total = len(stack_manager.image_paths)
            next_idx = self.current_index
            while next_idx == self.current_index:
                next_idx = random.randint(0, total - 1)
            direction = 1 
            if self.carousel.isVisible():
                self.carousel.slide(direction)
            self.current_index = next_idx
            self.update_image_source(with_fade=True)
        else:
            self.change_image(1, with_fade=True)

    def update_fade_progress(self, v):
        self.transition_progress = v
        self.update()

    def on_fade_finished_img(self):
        self.old_pixmap = None
        self.transition_progress = 0.0
        self.update()

    def update_image_source(self, with_fade=False):
        if not stack_manager.image_paths: return
        if with_fade and self.pixmap:
            self.old_pixmap = self.pixmap
            self.old_scale_factor = self.scale_factor
            self.transition_progress = 0.0
        idx = self.current_index % len(stack_manager.image_paths)
        path = stack_manager.image_paths[idx]
        pix = stack_manager.get_pixmap(path)
        if not pix.isNull():
            self.pixmap = pix
            # 画像切り替え時はFitさせる
            self.calculate_fit_scale()
            
            # カルーセル表示更新
            if self.manager.params['show_carousel'] and self.is_ui_visible:
                if self.carousel.anim_slide.state() == QAbstractAnimation.State.Running:
                    pass 
                else:
                    self.carousel.update_content()
                    self.carousel.update_position()
            
            self.update_satellites()
            if with_fade:
                self.fade_anim.start()
            else:
                self.fade_in_ui()
                self.update()

    def change_image(self, direction, with_fade=False):
        if not stack_manager.image_paths: return
        if self.carousel.isVisible():
            self.carousel.slide(direction)
        self.current_index += direction
        self.update_image_source(with_fade=with_fade)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if self.pixmap is None:
            bg_alpha = 50
        else:
            bg_alpha = int(50 * self.border_opacity)
        
        if bg_alpha > 0:
            painter.setBrush(QColor(0, 0, 0, bg_alpha))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(self.rect())

        if self.pixmap is None:
            pen = QPen(QColor(255, 255, 255, 255))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(self.rect().adjusted(1, 1, -1, -1))
            painter.setFont(QFont("Arial", 12))
            
            text = "Drop here"
            if self.manager: text = self.manager.tr('drop_text')
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)
            return

        border_w = 2
        area_rect = self.rect().adjusted(border_w, border_w, -border_w, -border_w)
        
        # ★ 変更: オフセットを使って描画
        # 画像サイズ
        img_w = self.pixmap.width() * self.scale_factor
        img_h = self.pixmap.height() * self.scale_factor
        
        # 描画位置 = 左上(0,0) + 余白(border) + オフセット
        # img_offset は (0,0) を基準とした相対位置とする
        # ただし、初期状態では中央に来るように calculate_fit_scale で調整する
        
        # 描画先 (QRectFを使用)
        target_x = area_rect.x() + self.img_offset.x()
        target_y = area_rect.y() + self.img_offset.y()
        
        # フェードアニメーション
        if self.old_pixmap and self.fade_anim.state() == QVariantAnimation.State.Running:
            painter.setOpacity(1.0 - self.transition_progress)
            
            # 古い画像も同じ位置・サイズで消えていくように描画
            # ★修正：保存しておいた old_scale_factor を使う
            w_old = self.old_pixmap.width() * self.old_scale_factor 
            h_old = self.old_pixmap.height() * self.old_scale_factor
            
            # 古い画像のオフセット位置を計算（簡易的には現在の枠位置に合わせつつサイズだけ維持）
            rect_old = QRectF(target_x, target_y, w_old, h_old)
            painter.drawPixmap(rect_old, self.old_pixmap, QRectF(self.old_pixmap.rect()))
            
            painter.setOpacity(self.transition_progress)
            target_rect = QRectF(target_x, target_y, img_w, img_h)
            painter.drawPixmap(target_rect, self.pixmap, QRectF(self.pixmap.rect()))
            painter.setOpacity(1.0)
        else:
            target_rect = QRectF(target_x, target_y, img_w, img_h)
            painter.drawPixmap(target_rect, self.pixmap, QRectF(self.pixmap.rect()))

        if self.border_opacity > 0:
            color = QColor(255, 255, 255)
            color.setAlphaF(self.border_opacity * 0.5)
            pen = QPen(color)
            pen.setWidth(2) 
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(1, 1, -1, -1))

    # --- 新しい操作ロジック ---

    def calculate_fit_scale(self):
        """画像をウィンドウ枠に合わせてFitさせ、設定されたアンカーに従って配置する"""
        if self.pixmap is None: return
        
        win_w = self.width() - 4
        win_h = self.height() - 4
        img_w = self.pixmap.width()
        img_h = self.pixmap.height()
        
        self.scale_factor = min(win_w / img_w, win_h / img_h)
        
        # 配置オフセット計算
        disp_w = img_w * self.scale_factor
        disp_h = img_h * self.scale_factor
        
        anchor = self.manager.params.get('anchor_mode', 'center')
        
        if anchor == 'top-left':
            off_x = 0
            off_y = 0
        elif anchor == 'top-right':
            off_x = win_w - disp_w
            off_y = 0
        elif anchor == 'bottom-left':
            off_x = 0
            off_y = win_h - disp_h
        elif anchor == 'bottom-right':
            off_x = win_w - disp_w
            off_y = win_h - disp_h
        else: # center
            off_x = (win_w - disp_w) / 2
            off_y = (win_h - disp_h) / 2
        
        self.img_offset = QPointF(off_x, off_y)

    def handle_resize(self, event):
        global_pos = event.globalPosition().toPoint()
        diff = global_pos - self.drag_pos
        geo = self.start_geometry
        new_geo = QRect(geo)
        
        # 1. 枠の変更量を計算
        dx, dy = 0, 0
        
        if 'right' in self.resize_edge: 
            new_geo.setRight(geo.right() + diff.x())
            dx = diff.x()
        if 'left' in self.resize_edge: 
            # 最小サイズを考慮した新しい左端を計算
            new_left = geo.left() + diff.x()
            if geo.right() - new_left < 50:
                new_left = geo.right() - 50
            new_geo.setLeft(new_left)
            dx = -diff.x() 
        if 'bottom' in self.resize_edge: 
            new_geo.setBottom(geo.bottom() + diff.y())
            dy = diff.y()
        if 'top' in self.resize_edge: 
            # 最小サイズを考慮した新しい上端を計算
            new_top = geo.top() + diff.y()
            if geo.bottom() - new_top < 50:
                new_top = geo.bottom() - 50
            new_geo.setTop(new_top)
            dy = -diff.y()

        # 最小サイズ制限は setLeft/setTop 時に考慮済みだが念のため
        if new_geo.width() < 50: new_geo.setWidth(50)
        if new_geo.height() < 50: new_geo.setHeight(50)
        
        # 2. 画像の調整 (枠のみリサイズの場合、オフセットを先行補正)
        if self.pixmap and self.resize_button == Qt.MouseButton.RightButton:
            # 実際にウィンドウが動いた量（リサイズの結果）を計算
            actual_moved_x = new_geo.left() - geo.left()
            actual_moved_y = new_geo.top() - geo.top()
            
            # ウィンドウの原点が動いた分だけ、画像を逆方向にずらす
            if actual_moved_x != 0:
                self.img_offset.setX(self.start_img_offset.x() - actual_moved_x)
            if actual_moved_y != 0:
                self.img_offset.setY(self.start_img_offset.y() - actual_moved_y)

        # 3. 適用 (画像の補正後に枠を動かすことで震えを防ぐ)
        self.setGeometry(new_geo)

        if self.pixmap and self.resize_button == Qt.MouseButton.LeftButton:
            # 左ドラッグ: 対称性を維持して拡大（Fit状態をキープ）
            self.calculate_fit_scale()
        
        # ★重要: 左上を動かした時の描画ズレ（揺れ）を防ぐため、即時描画する
        self.repaint()

    def check_hover_state(self):
        # ★ 追加: ダイアログ表示中はホバー反応を無効化
        if QApplication.activeModalWidget(): 
            if self.is_ui_visible:
                self.hide_timer.start(0) 
            return

        cursor_pos = QCursor.pos()
        main_hover = self.frameGeometry().contains(cursor_pos)
        carousel_hover = self.carousel.isVisible() and self.carousel.frameGeometry().contains(cursor_pos)
        
        if self.list_overlay.isVisible():
            if self.is_ui_visible:
                self.hide_timer.start(0) 
            return

        should_show = False
        
        if main_hover or carousel_hover:
            try:
                point = wintypes.POINT(cursor_pos.x(), cursor_pos.y())
                hwnd = ctypes.windll.user32.WindowFromPoint(point)
                
                pid = wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                
                if pid.value == os.getpid():
                    should_show = True
            except Exception:
                should_show = True 
        
        if should_show:
            if not self.is_ui_visible and not self.show_delay_timer.isActive():
                self.show_delay_timer.start()
            if self.is_ui_visible:
                self.hide_timer.stop()
        else:
            if self.show_delay_timer.isActive():
                self.show_delay_timer.stop()
            if self.is_ui_visible and not self.hide_timer.isActive() and self.border_opacity > 0:
                self.hide_timer.start(700)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.accept()

    def dropEvent(self, event):
        new_files_added = False
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')):
                stack_manager.add_image(path)
                new_files_added = True
        if new_files_added:
            self.current_index = len(stack_manager.image_paths) - 1
            self.update_image_source()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    window_manager = WindowManager()
    
    sys.exit(app.exec())