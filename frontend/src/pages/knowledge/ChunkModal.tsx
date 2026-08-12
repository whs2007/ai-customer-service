/** 新增 / 编辑 Chunk 弹窗（04 §4.4–4.5）。 */

import { Form, Input, Modal, Select } from 'antd';
import { useEffect } from 'react';

import type { ChunkItem } from '../../api/knowledge';

interface Props {
  open: boolean;
  editing?: ChunkItem | null;
  submitting: boolean;
  onCancel: () => void;
  onSubmit: (values: {
    question: string;
    answer: string;
    category?: string | null;
    tags?: string[];
    page?: string | null;
    row?: string | null;
  }) => void;
}

interface FormValues {
  question: string;
  answer: string;
  category?: string | null;
  tags?: string[];
  page?: string | null;
  row?: string | null;
}

export default function ChunkModal({ open, editing, submitting, onCancel, onSubmit }: Props) {
  const [form] = Form.useForm<FormValues>();

  useEffect(() => {
    if (open) {
      form.setFieldsValue({
        question: editing?.question ?? '',
        answer: editing?.answer ?? '',
        category: editing?.category ?? '',
        tags: editing?.tags ?? [],
        page: editing?.page ?? '',
        row: editing?.row ?? '',
      });
    }
  }, [open, editing, form]);

  return (
    <Modal
      title={editing ? '编辑 Chunk' : '添加 Chunk'}
      open={open}
      onCancel={onCancel}
      width={560}
      confirmLoading={submitting}
      onOk={() => form.submit()}
      destroyOnClose
    >
      <Form<FormValues> form={form} layout="vertical" onFinish={onSubmit} preserve={false}>
        <Form.Item
          name="question"
          label="问题"
          rules={[
            { required: true, message: '请输入问题' },
            { max: 200, message: '问题不超过 200 字' },
          ]}
        >
          <Input placeholder="问题" maxLength={200} showCount />
        </Form.Item>
        <Form.Item
          name="answer"
          label="答案"
          rules={[
            { required: true, message: '请输入答案' },
            { max: 2000, message: '答案不超过 2000 字' },
          ]}
        >
          <Input.TextArea placeholder="答案" rows={5} maxLength={2000} showCount />
        </Form.Item>
        <Form.Item name="category" label="分类">
          <Input placeholder="分类（可选）" maxLength={50} />
        </Form.Item>
        <Form.Item name="tags" label="标签">
          <Select
            mode="tags"
            placeholder="输入后回车添加（单个 ≤20 字，最多 10 个）"
            tokenSeparators={[',', '，']}
            maxCount={10}
          />
        </Form.Item>
        <div style={{ display: 'flex', gap: 16 }}>
          <Form.Item name="page" label="页码/来源" style={{ flex: 1 }}>
            <Input placeholder="如：第 2 页（可选）" maxLength={50} />
          </Form.Item>
          <Form.Item name="row" label="行号" style={{ flex: 1 }}>
            <Input placeholder="如：2（可选）" maxLength={50} />
          </Form.Item>
        </div>
      </Form>
    </Modal>
  );
}

