import type { Plugin } from "@opencode-ai/plugin";

export const validate: Plugin = async ({ $ }) => {
  return {
    "tool.execute.after": async (input) => {
      const tool = input.tool;
      const args = input.args as Record<string, unknown>;

      if (tool !== "write" && tool !== "edit") {
        return;
      }

      const filePath = (args.file_path as string) || (args.filePath as string);
      if (!filePath) {
        return;
      }

      const isKnowledgeJson = filePath.includes("knowledge/articles/") && filePath.endsWith(".json");
      if (!isKnowledgeJson) {
        return;
      }

      try {
        // 先验证
        await $`python3 hooks/validate_json.py ${filePath}`.nothrow();
        // 再检查质量
        await $`python3 hooks/check_quality.py ${filePath}`.nothrow();
      } catch (error) {
        // 吞掉异常，避免阻塞 OpenCode
      }
    },
  };
};
