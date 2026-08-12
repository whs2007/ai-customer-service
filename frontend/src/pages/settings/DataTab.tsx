/** 数据管理 Tab（07 §2）：分块参数 / 重建向量索引 / 导出知识库。 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Form, InputNumber, Modal, Space, message } from 'antd';
import { useEffect } from 'react';

import { ApiError } from '../../api/client';
import { exportKnowledgeBases, rebuildVectors } from '../../api/admin';
import { getChunkingConfig, updateChunkingConfig, type ChunkingConfig } from '../../api/settings';

export default function DataTab() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm<ChunkingConfig>();
  const { data } = useQuery({ queryKey: ['chunking-config'], queryFn: getChunkingConfig });
  useEffect(() => {
    if (data) form.setFieldsValue(data);
  }, [data, form]);

  const saveMutation = useMutation({
    mutationFn: updateChunkingConfig,
    onSuccess: () => {
      message.success('分块参数已更新（新上传文档生效）');
      queryClient.invalidateQueries({ queryKey: ['chunking-config'] });
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '保存失败'),
  });
  const rebuildMutation = useMutation({
    mutationFn: rebuildVectors,
    onSuccess: (r) => message.success(`向量重建完成：成功 ${r.succeeded} / 共 ${r.total}`),
    onError: (err) => message.error(err instanceof ApiError ? err.message : '重建失败'),
  });

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', maxWidth: 720 }}>
      <Card title="普通文本分块参数（04 §3.5）">
        <Form
          form={form}
          layout="inline"
          initialValues={{ chunk_size: 500, overlap: 50 }}
          onFinish={(v) => saveMutation.mutate(v)}
        >
          <Form.Item name="chunk_size" label="分块长度（字）">
            <InputNumber min={100} max={2000} />
          </Form.Item>
          <Form.Item name="overlap" label="重叠（字）">
            <InputNumber min={0} max={200} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
            保存
          </Button>
        </Form>
      </Card>

      <Card title="向量索引">
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="全量重建将重新解析并向量化所有文档，耗时随数据量增长；操作前请确认。"
        />
        <Space>
          <Button
            danger
            loading={rebuildMutation.isPending}
            onClick={() =>
              Modal.confirm({
                title: '全量重建向量索引',
                content: '将重新解析并向量化全部文档，期间检索结果可能短暂不完整。确定继续吗？',
                okText: '重建',
                okButtonProps: { danger: true },
                cancelText: '取消',
                onOk: () => rebuildMutation.mutate(),
              })
            }
          >
            全量重建向量索引
          </Button>
        </Space>
      </Card>

      <Card title="备份 / 导出">
        <Button type="primary" ghost onClick={() => void exportKnowledgeBases().catch(() => message.error('导出失败'))}>
          导出知识库（JSON）
        </Button>
        <div style={{ fontSize: 12, color: '#9CA3AF', marginTop: 8 }}>
          导出内容：知识库 + 文档 + Chunk 全量文本（不含向量，可重新向量化）
        </div>
      </Card>
    </Space>
  );
}
