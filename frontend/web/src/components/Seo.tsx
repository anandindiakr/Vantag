import { Helmet } from 'react-helmet-async';

export interface SeoProps {
  title: string;
  description: string;
  path: string; // e.g. "/", "/faq"
  image?: string;
  jsonLd?: Record<string, any> | Record<string, any>[];
  noindex?: boolean;
}

// The three live country domains for this product, used for canonical +
// hreflang cross-linking. x-default points at the India (primary) domain.
const DOMAINS = {
  in: 'https://retailnazar.com',
  sg: 'https://retail-vantag.com',
  my: 'https://jagajaga.my',
  id: 'https://retailpantau.com',
};

function currentOrigin(): string {
  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin;
  }
  return DOMAINS.in;
}

export default function Seo({ title, description, path, image, jsonLd, noindex }: SeoProps) {
  const origin = currentOrigin();
  const canonical = `${origin}${path}`;
  const ogImage = image || `${origin}/og-image.png`;

  const orgLd = {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: 'BrainGuardX AI Technologies Pvt. Ltd.',
    url: DOMAINS.in,
    logo: `${DOMAINS.in}/logo.png`,
  };

  const ldBlocks = Array.isArray(jsonLd) ? jsonLd : jsonLd ? [jsonLd] : [];

  return (
    <Helmet>
      <title>{title}</title>
      <meta name="description" content={description} />
      <link rel="canonical" href={canonical} />
      {noindex && <meta name="robots" content="noindex,nofollow" />}

      {/* hreflang cross-domain targeting */}
      <link rel="alternate" hrefLang="en-IN" href={`${DOMAINS.in}${path}`} />
      <link rel="alternate" hrefLang="en-SG" href={`${DOMAINS.sg}${path}`} />
      <link rel="alternate" hrefLang="ms-MY" href={`${DOMAINS.my}${path}`} />
      <link rel="alternate" hrefLang="id-ID" href={`${DOMAINS.id}${path}`} />
      <link rel="alternate" hrefLang="x-default" href={`${DOMAINS.in}${path}`} />

      {/* Open Graph */}
      <meta property="og:type" content="website" />
      <meta property="og:title" content={title} />
      <meta property="og:description" content={description} />
      <meta property="og:url" content={canonical} />
      <meta property="og:image" content={ogImage} />

      {/* Twitter */}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={title} />
      <meta name="twitter:description" content={description} />
      <meta name="twitter:image" content={ogImage} />

      {/* Structured data */}
      <script type="application/ld+json">{JSON.stringify(orgLd)}</script>
      {ldBlocks.map((block, i) => (
        <script key={i} type="application/ld+json">{JSON.stringify(block)}</script>
      ))}
    </Helmet>
  );
}
