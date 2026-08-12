/** 未选择知识库时的右侧空态（04 §1.4）。 */

import { Empty } from 'antd';

export default function KnowledgeEmpty() {
  return (
    <Empty
      style={{ marginTop: 120 }}
      description={
        <>
          <div>请选择知识库</div>
          <div style={{ fontSize: 12, color: '#9CA3AF', marginTop: 4 }}>
            选择左侧知识库查看文档
          </div>
        </>
      }
    />
  );
}

