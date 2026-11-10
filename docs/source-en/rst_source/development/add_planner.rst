Add a Planner
=============

A planner receives prompts, chooses tools, and consumes their results. To add one, subclass ``Planner``, implement ``solve``, and expose it through the construction path and CLI choices.

The following interface sketch omits model requests and the tool loop; it is not a runnable implementation. See ``rpent/planner/api_loop.py`` for a complete backend.

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
           # Call the model with system_prompt, user_message, and tools.
           # Execute each tool call through this interface:
           tool_result = toolkit.execute_tool(tool_name, arguments)
           ...
           return PlannerResult(
               finish_result=finish_result,
               messages=messages,
               stats=stats,
               error=error,
           )

Any planner must:

1. Accept the rendered ``system_prompt`` and ``user_message``.
2. Read each tool's ``name``, ``description``, and ``input_schema`` from
   ``toolkit.list_tools()`` and execute
   tools with ``toolkit.execute_tool(name, arguments)``.
3. Convert ``ToolResult.to_text()`` and PNG bytes in ``ToolResult.images`` to the
   format expected by the model SDK.
4. Detect ``ToolResult.data.get("_finish")`` and stop according to
   ``max_turns`` and any other limits.
5. Return a ``PlannerResult`` containing the finish state, messages,
   statistics, and an optional error.

Because the RPent tool schemas and prompt-rendering path stay the same,
adding a planner does not require changes to tools or environment
servers. See :doc:`architecture` for the interface, and
:doc:`add_primitive` if you want to expose new tools to
your custom planner.

Wire and Validate the Planner
-----------------------------

Add a construction branch in ``rpent/planner/base.py:build_planner`` and a CLI choice in ``rpent/cli/main.py``. If the planner supports Dashboard selection or connection diagnostics, wire those entry points and ``rpent/planner/check.py`` as well.

Verify tool dispatch, text and image results, ``finish``, turn limits, errors, and the interruption and interaction paths you support. Reuse test patterns in ``tests/unit_tests/rpent/planner/``. Validate real model connectivity separately.

.. _deepseek-runtime-bridge:

DeepSeek Harness Runtime Bridge
-------------------------------

The optional ``deepseek-harness`` extra pins both SDK and runtime to
``0.2.1rc2``. Compose it with ``HttpMcpServer(..., include_structured=True)``
and ``deepseek_tools._ToolBoundary`` to expose RPent tools. The boundary retains
native completion and execution certainty, and stops after uncertain execution
or failed result serialization. Pass the same ledger path to ``_ToolBoundary``
and the bridge's required ``toolLedgerPath`` setting.

The bridge requires a fresh, single-agent SDK runtime. It restricts calls to the
RPent allowlist, preserves the complete system prompt, and enforces the root-step
budget and exact model/provider/effort for root and summary requests. It checks
result delivery and image dimensions before another action. Callers must disable
non-RPent tools and extra agents, set ``agent-loop.maxParallelToolCalls`` to ``1``,
and require ``rpentBridgeReady`` in ``sdk-jsonrpc-server`` startup dependencies.

In pinned rc2, model input uses MCP ``content``; ``structuredContent`` is for
programmatic consumers. Long text remains bounded by RPent's text limit even
when the native result and structured copy are complete. Finite negative zero
is normalized only at the MCP boundary; non-finite values are rejected. Error
results containing images or incomplete text stop the run because rc2 cannot
deliver them intact.

The caller owns cancellation, Toolkit drain, SDK/process cleanup, and final
control-record interpretation. These components do not register an RPent
planner, expose host controls, or restore persisted sessions. The offline
``tests/unit_tests/rpent/planner/runtime/`` cases demonstrate startup, delivery,
images, compaction, retries, and cleanup. Their SDK inventory fixture pins all
100 profile entries; updating either dependency requires reviewing that inventory.

Both distributions declare MIT and include ``LICENSE``. The runtime also ships
``THIRD_PARTY_NOTICES.md`` for its bundled dependencies.
