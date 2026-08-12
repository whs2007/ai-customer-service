/** 检索测试页（05 §3–6 / 01 设计规范）。 */

import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
  message,
} from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { ApiError } from '../api/client';
import { listKnowledgeBases } from '../api/knowledge';
import {
  retrievalTest,
  type RetrievalHit,
  type RetrievalResponse,
  type RetrieverMode,
} from '../api/retrieval';

const SAMPLE_QUESTIONS = [
  '商品签收后几天可以退货？',
  '软件激活后还能退吗？',
  '退款审核通过后多久到账？',
];

const MODE_OPTIONS: { value: RetrieverMode; label: string }[] = [
  { value: 'vector', label: '向量检索' },
  { value: 'hybrid', label: '混合检索' },
  { value: 'hybrid_rerank', label: '混合+重排' },
];

/** 相关度颜色规则（05 §4.3，按 01 §4.1 语义色）：高分绿 / 中分橙 / 低分红 */
function scoreColor(score: number): string {
  if (score >= 70) return 'green';
  if (score >= 40) return 'orange';
  return 'red';
}

function scoreTag(label: string, score: number, isPercent: boolean) {
  const display = isPercent
    ? `${score % 1 === 0 ? score : score.toFixed(1)}%`
    : score.toFixed(4);
  return (
    <Tag color={scoreColor(isPercent ? score : score * 100)}>
      {label} {display}
    </Tag>
  );
}

export default function RecallTest() {
  const [kbIds, setKbIds] = useState<string[]>([]);
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(3);
  const [tags, setTags] = useState<string[]>([]);
  const [mode, setMode] = useState<RetrieverMode>('hybrid');
  const [result, setResult] = useState<RetrievalResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: knowledgeBases = [] } = useQuery({
    queryKey: ['knowledge-bases'],
    queryFn: listKnowledgeBases,
  });

  const kbNameMap = useMemo(
    () => Object.fromEntries(knowledgeBases.map((kb) => [kb.id, kb.name])),
    [knowledgeBases],
  );

  // 默认选中第一个知识库（05 §4.1）
  useEffect(() => {
    if (kbIds.length === 0 && knowledgeBases.length > 0) {
      setKbIds([knowledgeBases[0].id]);
    }
  }, [knowledgeBases, kbIds.length]);

  const search = useCallback(
    async (q?: string) => {
      const finalQuery = (q ?? query).trim();
      if (!finalQuery) {
        message.warning('请输入问题');
        return;
      }
      if (kbIds.length === 0) {
        message.warning('请至少选择一个知识库');
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const data = await retrievalTest({
          kb_ids: kbIds,
          query: finalQuery,
          top_k: topK,
          tags,
          retriever_mode: mode,
        });
        setResult(data);
      } catch (err) {
        setResult(null);
        setError(err instanceof ApiError ? err.message : '检索失败，请稍后重试');
      } finally {
        setLoading(false);
      }
    },
    [kbIds, query, topK, tags, mode],
  );

  // TopK / 知识库 / 标签 / 检索方式 / 问题变化后防抖自动重新检索（05 §6）
  useEffect(() => {
    if (!query.trim() || kbIds.length === 0) return;
    const timer = setTimeout(() => void search(), 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbIds, topK, tags, mode, query]);

  const fillSample = (sample: string) => {
    setQuery(sample);
  };

  // 重排前后对比（05 §4.3 建议视图）：按 retrieval_score 计算的原始名次
  const originalRankMap = useMemo(() => {
    if (!result || result.actual_mode !== 'hybrid_rerank') return new Map<string, number>();
    const byRetrieval = [...result.hits].sort((a, b) => b.retrieval_score - a.retrieval_score);
    return new Map(byRetrieval.map((h, i) => [h.chunk_id, i + 1]));
  }, [result]);

  return (
    <div>
      <h1 className="page-title">检索测试</h1>
      <p className="page-sub">
        RAG Recall Lab：输入问题、选择知识库与 TopK，查看召回片段与相关度（05_检索测试.md）
      </p>

      {/* 检索表单（05 §4.1） */}
      <Card style={{ marginTop: 16, borderRadius: 14, boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}>
        <Space wrap size={12}>
          <Select
            mode="multiple"
            placeholder="选择知识库"
            style={{ minWidth: 260 }}
            value={kbIds}
            onChange={setKbIds}
            options={knowledgeBases.map((kb) => ({ value: kb.id, label: kb.name }))}
            maxTagCount="responsive"
          />
          <Input
            placeholder="请输入您的问题或关键词…"
            style={{ width: 320 }}
            maxLength={200}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onPressEnter={() => void search()}
          />
          <Select
            value={topK}
            onChange={setTopK}
            options={Array.from({ length: 10 }, (_, i) => ({
              value: i + 1,
              label: `Top ${i + 1}`,
            }))}
            style={{ width: 90 }}
          />
          <Select
            mode="tags"
            placeholder="标签过滤"
            style={{ minWidth: 150 }}
            value={tags}
            onChange={setTags}
            tokenSeparators={[',', '，']}
            maxCount={10}
          />
          <Select
            value={mode}
            onChange={setMode}
            options={MODE_OPTIONS}
            style={{ width: 130 }}
          />
          <Button
            type="primary"
            icon={<SearchOutlined />}
            loading={loading}
            disabled={!query.trim()}
            onClick={() => void search()}
          >
            检索
          </Button>
        </Space>

        {/* 示例问题（05 §4.2） */}
        <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            快速测试：
          </Typography.Text>
          {SAMPLE_QUESTIONS.map((sample) => (
            <Tag
              key={sample}
              style={{ cursor: 'pointer' }}
              onClick={() => fillSample(sample)}
            >
              {sample}
            </Tag>
          ))}
        </div>
      </Card>

      {/* 模式降级提示（未配置重排 Key 自动降级） */}
      {result?.rerank_skipped && (
        <Alert
          style={{ marginTop: 16 }}
          type="warning"
          showIcon
          message="未配置重排 Key，已自动降级为混合检索（响应中 actual_mode=hybrid）"
        />
      )}

      {/* 召回结果区（05 §4.3） */}
      <div style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <Typography.Text strong style={{ fontSize: 16 }}>
            召回结果
          </Typography.Text>
          {result && (
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              {result.hits.length} 条命中
            </Typography.Text>
          )}
          {result && (
            <Tag color={result.actual_mode === 'hybrid_rerank' ? 'purple' : 'blue'}>
              {MODE_OPTIONS.find((m) => m.value === result.actual_mode)?.label}
            </Tag>
          )}
        </div>

        {error ? (
          <Alert
            type="error"
            showIcon
            message={error}
            action={
              <Button size="small" onClick={() => void search()}>
                重试
              </Button>
            }
          />
        ) : loading ? (
          <Card>
            <Skeleton active paragraph={{ rows: 4 }} />
          </Card>
        ) : !result ? (
          <Card>
            <Empty description="提交问题后会返回片段" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          </Card>
        ) : result.hits.length === 0 ? (
          <Card>
            <Empty description="0 条命中 / 暂无召回结果" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          </Card>
        ) : (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            {result.hits.map((hit: RetrievalHit, index: number) => {
              const originalRank = originalRankMap.get(hit.chunk_id);
              return (
                <Card
                  key={hit.chunk_id}
                  style={{ borderRadius: 14, boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}
                >
                  <div style={{ display: 'flex', gap: 16 }}>
                    <div
                      style={{
                        width: 32,
                        height: 32,
                        borderRadius: 8,
                        background: '#EFF6FF',
                        color: '#2563EB',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontWeight: 600,
                        flexShrink: 0,
                      }}
                    >
                      {index + 1}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <Typography.Text strong>{hit.question}</Typography.Text>
                        <span style={{ fontSize: 12, color: '#9CA3AF' }}>
                          {kbNameMap[hit.kb_id] ?? '知识库'} · {hit.document_name}
                          {hit.page ? ` · ${hit.page}` : ''}
                          {hit.row ? ` 行 ${hit.row}` : ''}
                        </span>
                      </div>
                      <Typography.Paragraph
                        style={{ marginTop: 8, marginBottom: 8, color: '#4B5563', fontSize: 14 }}
                        ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
                      >
                        {hit.answer}
                      </Typography.Paragraph>
                      <Space size={8}>
                        {scoreTag('检索分', hit.retrieval_score, true)}
                        {hit.rerank_score != null && scoreTag('重排分', hit.rerank_score, false)}
                        {originalRank != null && (
                          <Tag color="purple" style={{ marginLeft: 4 }}>
                            重排前 #{originalRank} → 重排后 #{index + 1}
                          </Tag>
                        )}
                      </Space>
                    </div>
                  </div>
                </Card>
              );
            })}
          </Space>
        )}
      </div>
    </div>
  );
}
