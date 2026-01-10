# 如何手动获取 Twitter Cookies

## 步骤 1: 安装浏览器扩展

### Chrome/Edge 用户：
推荐使用 **"Cookie-Editor"** 扩展
- 访问：https://chrome.google.com/webstore
- 搜索 "Cookie-Editor"
- 点击 "添加至 Chrome"

### Firefox 用户：
- 访问：https://addons.mozilla.org
- 搜索 "Cookie-Editor"
- 点击 "添加到 Firefox"

## 步骤 2: 登录 Twitter

1. 打开浏览器，访问 **https://twitter.com** (或 **https://x.com**)
2. 使用您的账号登录
3. 确保成功登录到主页

## 步骤 3: 导出 Cookies

### 使用 Cookie-Editor：
1. 在 Twitter 页面上，点击浏览器工具栏的 **Cookie-Editor 图标**
2. 点击右上角的 **"Export"** 按钮
3. 选择 **"Netscape"** 或 **"JSON"** 格式
4. 复制所有内容

### 或者使用开发者工具（适用于所有浏览器）：
1. 按 `F12` 打开开发者工具
2. 切换到 **"Application"** 标签 (Chrome) 或 **"Storage"** 标签 (Firefox)
3. 左侧菜单找到 **"Cookies"** > **"https://twitter.com"**
4. 找到名为 **"auth_token"** 的 cookie（这是最重要的）
5. 复制其值

## 步骤 4: 在应用中导入

1. 返回 Crypto Alpha Terminal 的 "🐦 Twitter Sentiment" 标签页
2. 选择 **"手动导入 Cookies"** 模式
3. 粘贴您复制的 cookies 内容
4. 点击 **"保存 Cookies"** 按钮

## 重要提示：

⚠️ **安全警告**：
- Cookies 包含您的登录凭证，**不要分享给他人**
- 定期更新 cookies（Twitter 会话可能过期）
- 如果遇到 "Unauthorized" 错误，请重新导出 cookies

✅ **验证成功**：
- 导入后，页面应显示 "✅ Logged in to Twitter"
- 您可以立即开始分析推文
