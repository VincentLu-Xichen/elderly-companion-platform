# 自由 LLM 主导 CBT 课程

这是与现有 `cbt_course` 隔离的实验实现。第一、二课由各自的 Prompt 根据完整本课对话历史自由推进；服务端只解析白名单控制标记，并负责持久化、审计和第二课本地安全拦截。

当前 freeform 分支的应用默认加载本包，路由导入为：

```python
from cbt_course_llm_freeform.router import register_course_routes
```

现有模板、API 路径、数据库表和 `/cbt-course-assets` 静态资源挂载保持不变。由其他课程实现创建的记录在本实现中只读。未完成课程固定报告 0% 和“LLM 自由引导”，完成后报告 100%。第二课每轮只调用模型一次，最多生成 600 tokens。

运行包内测试：

```powershell
.venv\Scripts\python.exe -m unittest discover cbt_course_llm_freeform\tests -v
```
