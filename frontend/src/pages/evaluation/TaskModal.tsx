/** 创建评测任务弹窗（09 §4.3）：评测集 + 对话模型 + 检索知识库。 */

import { useQuery } from '@tanstack/react-query';
import { Form, Modal, Select } from 'antd';
import { useEffect } from 'react';

import { listEvalSets } from '../../api/evaluation';
import { listKnowledgeBases } from '../../api/knowledge';
import { listModelProfiles } from '../../api/chat';

interface Props {
  open: boolean;
  submitting: boolean;
  onCancel: () => void;
  onSubmit: (values: {
    eval_set_id: string;
    model_profile_id?: string | null;
    kb_ids: string[];
  }) => void;
}

export default function TaskModal({ open, submitting, onCancel, onSubmit }: Props) {
  const [form] = Form.useForm();
  const { data: evalSets = [] } = useQuery({ queryKey: ['eval-sets'], queryFn: listEvalSets });
  const { data: knowledgeBases = [] } = useQuery({
    queryKey: ['knowledge-bases'],
    queryFn: listKnowledgeBases,
  });
  const { data: profiles = [] } = useQuery({
    queryKey: ['model-profiles'],
    queryFn: listModelProfiles,
  });
  const defaultProfile = profiles.find((p) => p.is_default) ?? profiles[0];

  useEffect(() => {
    if (open && defaultProfile) {
      form.setFieldsValue({ model_profile_id: defaultProfile.id });
    }
  }, [open, defaultProfile, form]);

  return (
    <Modal
      title="创建评测任务"
      open={open}
      onCancel={onCancel}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      width={520}
      destroyOnClose
    >
      <Form form={form} layout="vertical" onFinish={onSubmit} preserve={false}>
        <Form.Item
          name="eval_set_id"
          label="评测集"
          rules={[{ required: true, message: '请选择评测集' }]}
        >
          <Select
            placeholder="选择评测集"
            options={evalSets.map((s) => ({
              value: s.id,
              label: `${s.name}（${s.sample_count} 条）`,
              disabled: s.sample_count === 0,
            }))}
          />
        </Form.Item>
        <Form.Item name="model_profile_id" label="对话模型">
          <Select
            placeholder="默认对话模型"
            options={profiles.map((p) => ({
              value: p.id,
              label: `${p.name} · ${p.model}${p.is_default ? '（默认）' : ''}`,
            }))}
          />
        </Form.Item>
        <Form.Item
          name="kb_ids"
          label="检索知识库"
          rules={[{ required: true, message: '请至少选择一个知识库' }]}
        >
          <Select
            mode="multiple"
            placeholder="评测逐条回答使用的知识库"
            options={knowledgeBases.map((kb) => ({ value: kb.id, label: kb.name }))}
            maxTagCount="responsive"
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

