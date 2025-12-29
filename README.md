# FloatRef
A highly customizable, frameless image reference tool for Windows.
Windows向けのカスタマイズ性の高い、枠なし画像リファレンスツール。

## Overview / 概要
Provides flexible layer management, allowing you to keep images always on top or tucked behind other windows. Supports both static display and automated slideshows. With the dedicated "Switch Button" (always on top), you can toggle image visibility with a single click, ensuring a seamless workflow entirely manageable from the screen.

画像の最前面・最背面表示を自由に選択でき、固定表示からスライドショーまで幅広く対応。常に最前面に配置される「スイッチボタン」により、ワンクリックで画像の表示・非表示を切り替えられます。すべての操作が画面上で完結するように設計されており、作業を妨げません。
## Demo / デモ
<video src="https://github.com/user-attachments/assets/ac5d4d92-72dc-4b6a-b205-92b6191351a7" width="100%" controls></video>
## Features / 主な機能

- **Frameless Window**: Clean, borderless design.
- **Smart Resizing**: Standard resize (maintain aspect ratio) or crop mode.
- **Slideshow**: Automatic transitions with smooth fade effects.
- **Layer Management**: Always on top, normal, or always at bottom modes.
- **Carousel UI**: Quickly navigate through images with a visual thumbnail bar.
- **Gallery View**: Full-screen list view to select or open multiple images at once.
- **Switch Button**: A floating controller to toggle visibility and access menus.
- **Settings Persistence**: Saves window positions, scales, and offsets for your next session.
- **Multi-language Support**: Japanese and English interfaces.

## Requirements / 動作環境

- Python 3.x
- PyQt6

## Installation / インストール

```bash
pip install PyQt6
```

## How to Use / 使い方

- **Drop Images**: Drag and drop image files onto the window or switch button.
- **Move Window**: Right-click and drag inside the window.
- **Resize**: Left-drag edges for scaling, Right-drag edges for cropping.
- **Zoom**: Mouse wheel at cursor position.
- **Pan Image**: Middle-click and drag to move the image inside the frame.
- **Switch Button**: Left-click to hide/show all windows. Right-click for the main menu.

## License


This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.




