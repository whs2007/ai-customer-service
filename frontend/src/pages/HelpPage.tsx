/** 帮助文档页（07 §1）：左侧目录 + Markdown 渲染 + 锚点联动 + 搜索。 */

import { Input } from 'antd';
import { useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';

import { HELP_SECTIONS } from './help/content';

export default function HelpPage() {
  const [keyword, setKeyword] = useState('');
  const [activeId, setActiveId] = useState<string>(HELP_SECTIONS[0].id);
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});

  const sections = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    if (!kw) return HELP_SECTIONS;
    return HELP_SECTIONS.filter(
      (s) => s.title.toLowerCase().includes(kw) || s.markdown.toLowerCase().includes(kw),
    );
  }, [keyword]);

  // 滚动联动高亮当前章节
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActiveId(visible[0].target.id);
      },
      { rootMargin: '-80px 0px -70% 0px' },
    );
    Object.values(sectionRefs.current).forEach((el) => el && observer.observe(el));
    return () => observer.disconnect();
  }, [sections]);

  return (
    <div>
      <h1 className="page-title">帮助文档</h1>
      <p className="page-sub">系统使用说明：知识库、检索、对话、评测与会话标注（07_帮助文档与系统设置.md）</p>
      <div style={{ display: 'flex', gap: 16, marginTop: 16, alignItems: 'flex-start' }}>
        {/* 左侧目录 */}
        <div
          style={{
            width: 200,
            flexShrink: 0,
            background: '#FFFFFF',
            borderRadius: 14,
            boxShadow: '0 1px 3px rgba(0,0,0,.06)',
            padding: 12,
            position: 'sticky',
            top: 0,
          }}
        >
          <Input.Search
            placeholder="搜索文档"
            allowClear
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            style={{ marginBottom: 8 }}
          />
          {sections.length === 0 ? (
            <div style={{ color: '#9CA3AF', fontSize: 13, padding: 12 }}>无匹配内容</div>
          ) : (
            sections.map((s) => (
              <div
                key={s.id}
                onClick={() => {
                  setActiveId(s.id);
                  sectionRefs.current[s.id]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }}
                style={{
                  padding: '8px 10px',
                  borderRadius: 8,
                  fontSize: 13,
                  cursor: 'pointer',
                  marginBottom: 2,
                  background: activeId === s.id ? '#EFF6FF' : 'transparent',
                  color: activeId === s.id ? '#2563EB' : '#374151',
                }}
              >
                {s.title}
              </div>
            ))
          )}
        </div>

        {/* 右侧内容 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {sections.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 80, color: '#9CA3AF' }}>未找到匹配的文档内容</div>
          ) : (
            sections.map((s) => (
              <div
                key={s.id}
                id={s.id}
                ref={(el) => {
                  sectionRefs.current[s.id] = el;
                }}
                style={{
                  background: '#FFFFFF',
                  borderRadius: 14,
                  boxShadow: '0 1px 3px rgba(0,0,0,.06)',
                  padding: '20px 24px',
                  marginBottom: 16,
                }}
              >
                <ReactMarkdown
                  components={{
                    h1: ({ children }) => <h2 style={{ margin: '0 0 12px' }}>{children}</h2>,
                    h2: ({ children }) => <h3 style={{ margin: '16px 0 8px' }}>{children}</h3>,
                    code: ({ children }) => (
                      <code
                        style={{
                          background: '#F3F4F6',
                          padding: '2px 6px',
                          borderRadius: 6,
                          fontSize: 13,
                        }}
                      >
                        {children}
                      </code>
                    ),
                    blockquote: ({ children }) => (
                      <blockquote
                        style={{
                          borderLeft: '3px solid #3B82F6',
                          background: '#EFF6FF',
                          margin: '12px 0',
                          padding: '8px 12px',
                          color: '#374151',
                        }}
                      >
                        {children}
                      </blockquote>
                    ),
                  }}
                >
                  {s.markdown}
                </ReactMarkdown>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
