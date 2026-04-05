# PromptThrift MCP — 維護 SOP

## 更新流程

### 更新模型定價
1. 開啟 `server.py`，搜尋 `MODEL_PRICING`
2. 根據各家 API 最新定價更新數字
3. 執行測試：`python -m py_compile server.py`
4. 更新 README.md 的定價表
5. 提交：`git commit -am "chore: update model pricing YYYY-MM"`

### 新增模型支援
1. 在 `MODEL_PRICING` 字典加入新模型
2. 如需調整複雜度分析邏輯，更新 `analyze_complexity()`
3. 執行測試確認不會影響現有功能

### 發布新版本
```bash
git tag -a v0.1.x -m "Release notes"
git push origin main --tags
```

## 常見問題排查

| 問題 | 原因 | 解法 |
|------|------|------|
| MCP 連線失敗 | Python 路徑錯誤 | 確認 `claude_desktop_config.json` 的 python 路徑 |
| Import Error | 缺少依賴 | `pip install -r requirements.txt` |
| Token 計算不準 | 使用啟發式方法 | 這是估算值，誤差 ±10% 屬正常 |
| 壓縮效果不佳 | 對話太短 | 至少 8+ 輪對話才有明顯效果 |

## 備份策略
- 所有程式碼在 GitHub 上
- 無永久性資料需要備份（純運算工具）
- `.env` 不進 Git，需本地備份 API key

## 監控
- 日誌輸出到 stderr
- 查看 Claude Desktop 的 MCP 日誌確認運作狀態
