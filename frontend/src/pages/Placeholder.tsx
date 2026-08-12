/** 通用占位页：M1 阶段各业务页仅落地标题与空态，功能随后续里程碑实现。 */

import { Card, Empty } from 'antd';

interface PlaceholderProps {
  title: string;
  description: string;
  milestone: string;
}

export default function PlaceholderPage({ title, description, milestone }: PlaceholderProps) {
  return (
    <div>
      <h1 className="page-title">{title}</h1>
      <p className="page-sub">{description}</p>
      <div className="page-content">
        <Card>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <>
                <div>{milestone}</div>
                <div style={{ fontSize: 12, color: '#9CA3AF', marginTop: 4 }}>
                  本页面将在对应里程碑交付
                </div>
              </>
            }
          />
        </Card>
      </div>
    </div>
  );
}

