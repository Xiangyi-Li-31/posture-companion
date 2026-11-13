# 第三方项目说明

本项目通过 Python 包依赖使用以下项目，没有复制第三方仓库源码：

- [OpenCV](https://github.com/opencv/opencv)（Apache-2.0）：摄像头采集、颜色转换和画面标注。
- [MediaPipe](https://github.com/google-ai-edge/mediapipe)（Apache-2.0）：Pose Landmarker 与 33 个身体关键点模型。
- [Pillow](https://github.com/python-pillow/Pillow)（HPND）：在 Tkinter 中显示摄像头预览。
- [pystray](https://github.com/moses-palmer/pystray)（LGPL-3.0）：Windows 系统托盘图标与菜单。
- [Windows-Toasts](https://github.com/DatGuy1/Windows-Toasts)（MIT）：Windows 原生通知。
- [PyInstaller](https://github.com/pyinstaller/pyinstaller)（GPL-2.0-or-later，带打包例外）：生成 Windows 可执行程序。

设计时还阅读了 [forward_head_posture_alert](https://github.com/YoussefNim/forward_head_posture_alert)
的公开说明，用于了解同类工具常见的降负载和设置持久化思路；本项目的实现与代码结构为独立编写。
