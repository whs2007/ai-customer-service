/** 导入样本弹窗（09 §4.2）：逐条录入 / JSON 批量 / 一键导入 30 条公开样例。 */

import { Button, Form, Input, Modal, Space, Tabs, message } from 'antd';
import { useState } from 'react';

import { ApiError } from '../../api/client';
import { addSample, importPublicSamples, importSamples } from '../../api/evaluation';

interface Props {
  open: boolean;
  setId: string;
  onDone: () => void;
  onCancel: () => void;
}

export default function SampleModal({ open, setId, onDone, onCancel }: Props) {
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<{ question: string; expected_answer: string }>();

  const run = async (fn: () => Promise<unknown>, successMsg: string) => {
    setSubmitting(true);
    try {
      await fn();
      message.success(successMsg);
      onDone();
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '操作失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="导入样本"
      open={open}
      onCancel={onCancel}
      footer={null}
      width={640}
      destroyOnClose
    >
      <Tabs
        items={[
          {
            key: 'single',
            label: '逐条录入',
            children: (
              <Form
                form={form}
                layout="vertical"
                onFinish={(values) =>
                  run(
                    () => addSample(setId, values),
                    '样本已添加',
                  )
                }
              >
                <Form.Item
                  name="question"
                  label="问题"
                  rules={[{ required: true, message: '请输入问题' }, { max: 500, message: '问题不超过 500 字' }]}
                >
                  <Input placeholder="问题" maxLength={500} />
                </Form.Item>
                <Form.Item
                  name="expected_answer"
                  label="期望答案"
                  rules={[{ required: true, message: '请输入期望答案' }]}
                >
                  <Input.TextArea placeholder="期望答案" rows={3} maxLength={2000} />
                </Form.Item>
                <Button type="primary" htmlType="submit" loading={submitting}>
                  添加
                </Button>
              </Form>
            ),
          },
          {
            key: 'json',
            label: 'JSON 批量导入',
            children: <JsonImport setId={setId} run={run} submitting={submitting} />,
          },
          {
            key: 'public',
            label: '内置公开样例',
            children: (
              <div style={{ textAlign: 'center', padding: 24 }}>
                <p style={{ color: '#6B7280' }}>
                  一键导入首批 30 条公开样例（电商售后 FAQ：退换货/退款/物流/投诉等）
                </p>
                <Button
                  type="primary"
                  loading={submitting}
                  onClick={() =>
                    run(() => importPublicSamples(setId), '成功导入 30 条公开样例')
                  }
                >
                  导入 30 条公开样例
                </Button>
              </div>
            ),
          },
        ]}
      />
    </Modal>
  );
}

function JsonImport({
  setId,
  run,
  submitting,
}: {
  setId: string;
  run: (fn: () => Promise<unknown>, msg: string) => Promise<void>;
  submitting: boolean;
}) {
  const [text, setText] = useState('');
  const submit = () => {
    let items: { question: string; expected_answer: string }[];
    try {
      items = JSON.parse(text);
      if (!Array.isArray(items) || items.length === 0) throw new Error();
    } catch {
      message.error('JSON 格式不正确，应为数组：[{"question":"...","expected_answer":"..."}]');
      return;
    }
    void run(() => importSamples(setId, items), `成功导入 ${items.length} 条样本`);
  };
  return (
    <div>
      <Input.TextArea
        rows={8}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder='[{"question":"问题1","expected_answer":"期望答案1"}, ...]'
        style={{ fontFamily: 'monospace' }}
      />
      <Space style={{ marginTop: 12 }}>
        <Button type="primary" loading={submitting} onClick={submit}>
          导入
        </Button>
        <Button onClick={() => setText('')}>清空</Button>
      </Space>
    </div>
  );
}

