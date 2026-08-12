/** Prompt 配置 Tab（07 §2）：系统人设 / 兜底话术 / 转人工判定规则。 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Card, Form, Input, Space, message } from 'antd';

import { ApiError } from '../../api/client';
import { getPromptConfig, updatePromptConfig, type PromptConfig } from '../../api/settings';

const DEFAULTS: PromptConfig = {
  system_prompt:
    '你是 AI 智能客服，回答需基于知识库引用，不得编造；引用来源用 [1][2] 编号标注。',
  fallback_text: '抱歉，我暂时无法回答这个问题。您可以尝试换个问法，或转人工客服。',
  escalation_rule_text: '连续 2 次无法回答或用户投诉/明确要求转人工时，转人工并创建工单。',
};

export default function PromptTab() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm<PromptConfig>();
  const { data } = useQuery({
    queryKey: ['prompt-config'],
    queryFn: getPromptConfig,
  });

  const saveMutation = useMutation({
    mutationFn: (values: PromptConfig) => updatePromptConfig(values),
    onSuccess: () => {
      message.success('Prompt 配置已更新（对新会话生效）');
      queryClient.invalidateQueries({ queryKey: ['prompt-config'] });
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '保存失败'),
  });

  return (
    <Card style={{ maxWidth: 760 }}>
      <Form<PromptConfig>
        form={form}
        layout="vertical"
        initialValues={data ?? DEFAULTS}
        onFinish={(values) => saveMutation.mutate(values)}
      >
        <Form.Item name="system_prompt" label="系统人设">
          <Input.TextArea rows={3} maxLength={2000} showCount />
        </Form.Item>
        <Form.Item name="fallback_text" label="兜底话术（AI 无法回答时的回复）">
          <Input.TextArea rows={2} maxLength={500} showCount />
        </Form.Item>
        <Form.Item name="escalation_rule_text" label="转人工判定规则（说明文案）">
          <Input.TextArea rows={2} maxLength={500} showCount />
        </Form.Item>
        <Space>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
            保存
          </Button>
          <Button
            onClick={() => {
              form.setFieldsValue(DEFAULTS);
              saveMutation.mutate(DEFAULTS);
            }}
          >
            恢复默认
          </Button>
        </Space>
      </Form>
    </Card>
  );
}

