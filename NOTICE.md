# 依赖与第三方组件说明

本项目（安装向导、脚本、文档）以 **GPL-3.0** 发布，见 [LICENSE](LICENSE)。

## 分发包里的 APK

套件中的两个接收端 APK **均为上游项目的原样构建产物**，未做任何修改、未重新签名，
按 GPL-3.0 随本套件一起分发。它们的版权归各自作者所有。

| 文件 | 上游项目 | 版本 | 许可证 | 对应源码 |
|---|---|---|---|---|
| `AirPlay接收-精简版.apk` | [gzhanlei/uxplay-android](https://github.com/gzhanlei/uxplay-android) | v1.2.1 | GPL-3.0 | https://github.com/gzhanlei/uxplay-android/tree/v1.2.1 |
| `AirPlay接收-全功能版.apk` | [jqssun/android-airplay-server](https://github.com/jqssun/android-airplay-server) | v0.0.36 | GPL-3.0 | https://github.com/jqssun/android-airplay-server/tree/v0.0.36 |

两个 APK 的 SHA-256 固定记录在 [`scripts/fetch_apks.py`](scripts/fetch_apks.py)，
发布流程会重新校验，防止上游产物被替换。

### 上游 APK 内部包含的组件

接收端内部把 AirPlay 协议栈和若干库静态链接进了 `libairplay_native.so` / `libairplay-jni.so`：

- [UxPlay](https://github.com/FDH2/UxPlay) — AirPlay / RAOP 协议栈，GPL-3.0
- FFmpeg — LGPL/GPL（按上游构建配置）
- OpenSSL — Apache-2.0
- libplist — LGPL-2.1
- Oboe、AndroidX — Apache-2.0

这些组件的许可证与源码说明以上游项目为准。

## GPL 合规说明

- 本仓库不存储 APK 二进制，`scripts/fetch_apks.py` 从上游 Releases 下载并校验；
- 分发 zip 中的 APK 可追溯到上面的「对应源码」链接，满足 GPL-3.0 对源码获取的要求；
- 如果你需要完全离线地再分发，请一并保存上述 tag 的源码包。

## 商标

「AirPlay」「Apple TV」「iPhone」「iPad」「Mac」是 Apple Inc. 的商标；
「BRAVIA」「Sony」是 Sony Group Corporation 的商标。
本项目与 Apple、Sony 均无关联，也未获其背书。
