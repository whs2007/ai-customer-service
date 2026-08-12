/** 创建 / 编辑知识库弹窗（04 §2）。 */

import { Form, Input, Modal } from 'antd';
import { useEffect } from 'react';

import type { KnowledgeBase } from '../../api/knowledge';

interface Props {
  open: boolean;
  editing?: KnowledgeBase | null;
  submitting: boolean;
  onCancel: () => void;
  onSubmit: (values: { name: string; description: string }) => void;
}

interface FormValues {
  name: string;
  description: string;
}

export default function KnowledgeBaseModal({
  open,
  editing,
  submitting,
  onCancel,
  onSubmit,
}: Props) {
  const [form] = Form.useForm<FormValues>();

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
      title={editing ? '编辑知识库' : '创建知识库'}
      open={open}
      onCancel={onCancel}
      width={480}
      confirmLoading={submitting}
      onOk={() => form.submit()}
      destroyOnClose
    >
      <Form<FormValues>
        form={form}
        layout="vertical"
        onFinish={onSubmit}
        preserve={false}
      >
        <Form.Item
          name="name"
          label="名称"
          rules={[
            { required: true, message: '请输入知识库名称' },
            { max: 50, message: '名称不超过 50 字' },
          ]}
        >
          <Input placeholder="例如：知识库" maxLength={50} showCount />
        </Form.Item>
        <Form.Item
          name="description"
          label="描述"
          rules={[{ max: 200, message: '描述不超过 200 字' }]}
        >
          <Input.TextArea
            placeholder="描述知识库的功能"
            rows={3}
            maxLength={200}
            showCount
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

