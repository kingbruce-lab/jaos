# v1.7.1 白色LOGO补丁部署验收

- 北京时间2026-10-26发布。已读取云端“JAOS运营系统”最新改版，正式代码 `4dcc6a66851875b45632a648f8e264d08da05d43`，标签 `jaos-v1.7.1`；从同一干净提交在本地按仓库脚本重打NAS包。
- 应用差异仅为深色侧栏LOGO使用 `brightness(0) invert(1)` 显示为白色；展开及收起保留透明度、轮廓、尺寸和比例。
- 本地生产构建及33项前端、268项后端测试通过；桌面、平板和四种手机横竖屏导航回归通过。已查看桌面导航截图确认白色标记清晰。既有全仓lint/TypeScript诊断未变，未宣称通过。
- 实际发布包 `jaos-v1.7.1-nas-20261026-132321.zip`，SHA-256 `E9D3A9C9EDD37F842AEACB8CCDC18175F043533AD6C95A472B628C4346E4763F`，上传及包内清单校验通过。[Release与包](https://github.com/kingbruce-lab/jaos/releases/tag/jaos-v1.7.1) 已上传本地实际部署归档及.sha256。
- 发布前数据库专项备份 `/vol1/@team/京奥智库/02_备份/cost-center-predeploy-20261026T052312Z/database.dump`，88,744,911字节；SHA-256 `DF0BC908E08994F1EA19D308C892BDE6A8D460EA11FF2227E1C31E94B946B98F`；pg_restore目录校验通过（447行）。未进行临时库恢复演练，不是全量资料备份。
- 当前源码 `/vol1/@team/京奥智库/00_部署/releases/jaos-v1.7.1-20261026-132321`；上一源码 `/vol1/@team/京奥智库/00_部署/releases/jaos-v1.7.0-20261026-130413`。原配置保留，无数据库迁移或业务数据变更。
- 后端及依赖与v1.7.0比对一致，保持原Agent运行；离线构建新版Web镜像 `sha256:18455573f8fc9703a586470912458b61899ed310fc04ab2e333898c2652e37c2`。保留旧镜像 `jingao-web:base-v170` 和 `jingao-agent:rollback-v170`；发布后仅重建web服务。
- 线上VERSION=1.7.1，Web running/healthy；内部及公网首页200，真实历史批次65行元数据只读检查通过。
- 公网 `/assets/index-B8DEh_nu.css` 返回200，含白色LOGO滤镜，SHA-256与NAS容器一致：`c5f249044e0fd10b6e2367ed812104ac19080670b822fcc5a64c62562944d0c9`。压缩后 `invert()` 等价于 `invert(1)`，验证同时兼容这两种合法表示。
- 遗留告警仍在：NAS余约73GB（df四舍五入100%），/readyz=503来自storage critical及完整备份时效warning；数据库与内存正常。本次专项数据库备份不解除全量备份时效告警。未修改阈值、清理文件或回滚。
- 结论：v1.7.1白色LOGO补丁已上线且公网资源验证通过；上述既有运维告警仍待独立处理。
