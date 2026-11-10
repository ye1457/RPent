添加规划器
===============

规划器负责接收提示词、选择工具并处理工具结果。接入自定义规划器时，继承 ``Planner`` 并实现 ``solve``，然后将其加入构建入口和 CLI 选项。

以下为接口示意，省略了模型请求和工具循环，不能直接作为实现运行。完整示例可参考 ``rpent/planner/api_loop.py``。

.. code-block:: python

   # rpent/planner/my_planner.py
   from rpent.planner.base import Planner, PlannerResult

   class MyPlanner(Planner):
       def solve(
           self,
           *,
           system_prompt,
           user_message,
           toolkit,
           max_turns,
           input_queue=None,
           dashboard_interaction=None,
       ):
           tools = toolkit.list_tools()
           # 使用 system_prompt、user_message 和 tools 调用模型。
           # 每次工具调用都通过下面的接口执行：
           tool_result = toolkit.execute_tool(tool_name, arguments)
           ...
           return PlannerResult(
               finish_result=finish_result,
               messages=messages,
               stats=stats,
               error=error,
           )

任何 planner 必须：

1. 接收已经渲染好的 ``system_prompt`` 和 ``user_message``。
2. 从 ``toolkit.list_tools()`` 取得工具的 ``name``、``description`` 和 ``input_schema``，并通过 ``toolkit.execute_tool(name, arguments)`` 执行工具。
3. 将 ``ToolResult.to_text()`` 的文本和 ``ToolResult.images`` 中的 PNG 字节转换成模型 SDK 所需的格式。
4. 识别 ``ToolResult.data.get("_finish")``，并按 ``max_turns`` 等限制终止循环。
5. 返回包含结束状态、消息、统计信息和可选错误的 ``PlannerResult``。

由于 RPent 工具定义和 prompt 渲染流程保持不变，新增 planner 不需要修改工具或环境服务。接口参见 :doc:`architecture`；想给
自定义 planner 暴露新工具，见 :doc:`add_primitive`。

接入与验证
---------------

在 ``rpent/planner/base.py`` 的 ``build_planner`` 中添加构建分支，并在 ``rpent/cli/main.py`` 的 ``--planner`` 选项中加入名称。需要 Dashboard 或连接诊断时，还应接入对应的规划器选择与 ``rpent/planner/check.py``，不能仅添加一个类。

验证工具调用、文本和图像返回、``finish``、轮数上限、错误结果，以及需要支持的中断和交互路径。复用 ``tests/unit_tests/rpent/planner/`` 中的测试模式；真实模型连接需要单独验证。

.. _deepseek-runtime-bridge:

DeepSeek Harness 运行时桥接
--------------------------------------

可选依赖 ``deepseek-harness`` 将 SDK 和运行时都固定为 ``0.2.1rc2``。
通过 ``HttpMcpServer(..., include_structured=True)`` 与 ``deepseek_tools._ToolBoundary``
可向运行时提供 RPent 工具。边界保留原生完成状态和执行确定性，并在执行不确定或结果序列化失败时停止后续调用。
``_ToolBoundary`` 与桥接必填配置 ``toolLedgerPath`` 必须使用同一账本路径。

桥接要求全新、单 Agent 的 SDK 运行时。它只开放 RPent 工具白名单，保留完整系统提示，
限制根模型步骤预算，并保持根请求与摘要请求的模型、提供方和推理强度一致。
允许下一动作前，还会检查结果交付和图像尺寸。调用方必须关闭非 RPent 工具与额外 Agent，
将 ``agent-loop.maxParallelToolCalls`` 设为 ``1``，并把 ``rpentBridgeReady``
加入 ``sdk-jsonrpc-server`` 的启动依赖。

固定版本 rc2 将 MCP 的 ``content`` 送入模型； ``structuredContent`` 供程序读取。
即使原生结果和结构化副本完整，长文本仍受 RPent 文本上限约束。
有限负零只在 MCP 边界规范为零，非有限数值会被拒绝。
附图或文本不完整的错误结果会停止本轮，因为 rc2 无法完整交付这些结果。

调用方负责取消、等待 Toolkit 活动调用结束、回收 SDK 进程和解释最终控制记录。
这些组件不注册 RPent 规划器，不提供 host 控制通道，也不恢复持久化会话。
``tests/unit_tests/rpent/planner/runtime/`` 中的离线测试覆盖启动、交付、图像、压缩、重试和清理。
SDK 清单夹具固定了 profile 的全部 100 项；升级任一依赖时应重新核对清单。

SDK 与运行时分发包均声明 MIT 并附带 ``LICENSE``；运行时另附
``THIRD_PARTY_NOTICES.md``，列明内嵌依赖的许可。
