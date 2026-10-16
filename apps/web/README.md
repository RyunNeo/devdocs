# Web 前端

Next.js App Router / TypeScript / Tailwind。第一阶段页面已实现，其他目录为后续预留。

根目录执行 npm.cmd ci、npm.cmd run dev，默认前端为 127.0.0.1:3001。
配置读取 apps/web/.env.local，参考 .env.example。
API_BASE_URL 是服务端配置，浏览器使用 /api 前缀，经 Next.js 转发到 FastAPI。

- app/(auth)：登录、注册。
- app/(workspace)：服务端验证身份的布局，dashboard 已实现。
- components/auth：认证表单和退出交互。
- lib/auth.ts：请求级缓存的服务端身份查询。
- lib/api.ts：浏览器 JSON 请求与错误处理。
- tests/e2e：真实数据库账号流程和响应式布局验证。
- public：公开静态资源，禁止存放私有上传。

环境配置与重启步骤见根目录 outputs/stage-01-guide.md。
