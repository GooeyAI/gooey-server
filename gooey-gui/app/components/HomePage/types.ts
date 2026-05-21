export type ChatPreview = {
  type: "chat";
  userMessage: string | null;
  botMessage: string | null;
};

export type MediaPreview = {
  type: "image" | "video" | "audio";
  url: string;
  previewImg: string | null;
  caption: string | null;
};

export type IconPreview = {
  type: "icon";
  imageUrl: string | null;
  emoji: string | null;
};

export type CardPreview = ChatPreview | MediaPreview | IconPreview;

export type AccessBadge = {
  iconHtml: string;
  label: string;
};

export type CardData = {
  title: string;
  href: string;
  workflowLabel?: string;
  workflowEmoji?: string;
  description?: string;
  authorName?: string;
  authorPhotoUrl?: string | null;
  preview?: CardPreview;
  updatedAt?: string;
  runCount?: number;
  accessBadge?: AccessBadge;
};

export type WorkflowTab = {
  id: number;
  title: string;
  icon: string;
  cards: CardData[];
};

export type IndustryTile = {
  id: number;
  tagId: number;
  name: string;
  icon: string;
  description: string;
  workflowCount: number;
  href: string;
};

export type NewsItem = {
  id: number;
  headline: string;
  tag: string;
  photoUrl: string | null;
  age: string;
  href: string;
};
