# 共享契约

types 中存放前端使用的 API 数据结构，按阶段定义字段。当前仅为空模块。
Python schemas 是后端实际契约；完善 OpenAPI 后可生成 TypeScript 类型，
避免人工维护两套字段造成不一致。当前不建立可发布包或工作区依赖。
