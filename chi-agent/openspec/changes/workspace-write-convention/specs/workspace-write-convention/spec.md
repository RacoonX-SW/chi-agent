# 工作区写入契约

## 需求：路径约定必须可见

### 场景：写入合法路径
给定工作区根与 `<case_id>/<role>/<file>`（role 为 provider/payer/cm）或 `<case_id>/shared/<file>`，工具应写入成功并返回 `workspace file written`；缺失的父目录由工具创建。

### 场景：路径不符合约定
`<case_id>/care-manager/<file>`、跨角色目录或工作区外路径必须被拒绝，且不创建文件。

### 场景：符号链接逃逸
父目录是指向工作区外的符号链接时，工具必须拒绝并返回错误，外部路径不得出现文件。
