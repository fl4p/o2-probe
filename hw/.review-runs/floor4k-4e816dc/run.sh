#!/bin/zsh
export PATH=/opt/homebrew/bin:$PATH
export PLAYWRIGHT_MCP_EXTENSION_TOKEN="$(security find-generic-password -s playwright-mcp-extension-token -w)"
cd /Users/fab/dev/ee/hw/o2-probe/firmware
~/.local/bin/codex exec -s workspace-write \
  -c model_reasoning_effort=xhigh \
  -c sandbox_workspace_write.network_access=true \
  -c 'mcp_servers.playwright.command="npx"' \
  -c 'mcp_servers.playwright.args=["-y","@playwright/mcp@latest","--cdp-endpoint","http://127.0.0.1:56480"]' \
  -c 'mcp_servers.playwright.default_tools_approval_mode="approve"' \
  -c 'mcp_servers.fabchrome.command="npx"' \
  -c 'mcp_servers.fabchrome.args=["-y","@playwright/mcp@latest","--extension"]' \
  -c 'mcp_servers.fabchrome.env_vars=["PLAYWRIGHT_MCP_EXTENSION_TOKEN"]' \
  -c 'mcp_servers.fabchrome.default_tools_approval_mode="approve"' \
  --skip-git-repo-check - < "/Users/fab/dev/ee/hw/o2-probe/.review-runs/floor4k-4e816dc/prompt.txt" > "/Users/fab/dev/ee/hw/o2-probe/.review-runs/floor4k-4e816dc/review.log" 2>&1
echo $? > "/Users/fab/dev/ee/hw/o2-probe/.review-runs/floor4k-4e816dc/EXITED"
