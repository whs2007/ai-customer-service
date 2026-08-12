/** 创建 / 编辑评测集弹窗（09 §4.2）。 */

import { Form, Input, Modal } from 'antd';
import { useEffect } from 'react';

import type { EvalSet } from '../../api/evaluation';

interface Props {
  open: boolean;
  editing?: EvalSet | null;
  submitting: boolean;
  onCancel: () => void;
  onSubmit: (values: { name: string; description: string }) => void;
}

export default function EvalSetModal({ open, editing, submitting, onCancel, onSubmit }: Props) {
  const [form] = Form.useForm<{ name: string; description: string }>();
  useEffect(() => {
    if (open) {
      form.setFieldsValue({
        name: editing?.name ?? '',
        description: editing?.description ?? '',
      });
    }
  }, [open, editing, form]);
  return (
    <Modal
      title={editing ? '编辑评测集' : '创建评测集'}
      open={open}
      onCancel={onCancel}
      onOk={() => form.submit()}
      confirmLoading={submitting}
      width={480}
      destroyOnClose
    >
      <Form form={form} layout="vertical" onFinish={onSubmit} preserve={false}>
        <Form.Item
          name="name"
          label="名称"
          rules={[
            { required: true, message: '请输入评测集名称' },
            { max: 100, message: '名称不超过 100 字' },
          ]}
        >
          <Input placeholder="例如：售后知识库回归集" maxLength={100} showCount />
        </Form.Item>
        <Form.Item
          name="description"
          label="描述"
          rules={[{ max: 200, message: '描述不超过 200 字' }]}
        >
          <Input.TextArea placeholder="描述该评测集的覆盖范围" rows={3} maxLength={200} showCount />
        </Form.Item>
      </Form>
    </Modal>
  );
}

