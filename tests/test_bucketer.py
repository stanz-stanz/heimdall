"""Tests for bucketer: classify() and assign_buckets()."""


from src.prospecting.bucketer import assign_buckets, classify

# ---------------------------------------------------------------------------
# 1. WordPress → Bucket A
# ---------------------------------------------------------------------------

class TestBucketA:
    def test_wordpress_site_bucket_a(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(cms="WordPress", tech_stack=["WordPress:6.9.4", "PHP"])
        assert classify(company, scan) == "A"

    def test_woocommerce_in_tech_stack_bucket_a(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(cms="", tech_stack=["WooCommerce", "PHP"])
        assert classify(company, scan) == "A"


# ---------------------------------------------------------------------------
# 2. Joomla → Bucket B
# ---------------------------------------------------------------------------

class TestBucketB:
    def test_joomla_site_bucket_b(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(cms="Joomla", tech_stack=["Joomla", "PHP"])
        assert classify(company, scan) == "B"

    def test_drupal_site_bucket_b(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(cms="Drupal", tech_stack=["Drupal", "PHP"])
        assert classify(company, scan) == "B"


# ---------------------------------------------------------------------------
# 3. Shopify → Bucket C
# ---------------------------------------------------------------------------

class TestBucketC:
    def test_shopify_site_bucket_c(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(cms="Shopify", tech_stack=["Shopify"])
        assert classify(company, scan) == "C"

    def test_squarespace_site_bucket_c(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(cms="Squarespace", tech_stack=["Squarespace"])
        assert classify(company, scan) == "C"


# ---------------------------------------------------------------------------
# 4. No CMS but tech stack → Bucket E
# ---------------------------------------------------------------------------

class TestBucketE:
    def test_no_cms_with_tech_stack_bucket_e(self, sample_company, sample_scan_result):
        company = sample_company()
        scan = sample_scan_result(cms="", tech_stack=["Nginx", "React"], server="nginx/1.24")
        assert classify(company, scan) == "E"


# ---------------------------------------------------------------------------
# 5. No scan result → Bucket D
# ---------------------------------------------------------------------------

class TestBucketD:
    def test_no_scan_result_bucket_d(self, sample_company):
        company = sample_company()
        assert classify(company, None) == "D"

    def test_discarded_company_bucket_d(self, sample_company, sample_scan_result):
        company = sample_company()
        company.discard_reason = "no_email"
        scan = sample_scan_result(cms="WordPress")
        assert classify(company, scan) == "D"


# ---------------------------------------------------------------------------
# 6. Mixed batch — assign_buckets()
# ---------------------------------------------------------------------------

class TestAssignBuckets:
    def test_mixed_batch_distribution(self, sample_company, sample_scan_result):
        companies = [
            sample_company(cvr="11111111", website_domain="wp-site.dk"),
            sample_company(cvr="22222222", website_domain="joomla-site.dk"),
            sample_company(cvr="33333333", website_domain="shopify-site.dk"),
            sample_company(cvr="44444444", website_domain="custom-site.dk"),
            sample_company(cvr="55555555", website_domain=""),
        ]

        scan_results = {
            "wp-site.dk": sample_scan_result(domain="wp-site.dk", cms="WordPress", tech_stack=["WordPress:6.9.4"]),
            "joomla-site.dk": sample_scan_result(domain="joomla-site.dk", cms="Joomla", tech_stack=["Joomla"]),
            "shopify-site.dk": sample_scan_result(domain="shopify-site.dk", cms="Shopify", tech_stack=["Shopify"]),
            "custom-site.dk": sample_scan_result(domain="custom-site.dk", cms="", tech_stack=["Nginx", "React"], server="nginx"),
        }

        buckets = assign_buckets(companies, scan_results)

        assert buckets["11111111"] == "A"
        assert buckets["22222222"] == "B"
        assert buckets["33333333"] == "C"
        assert buckets["44444444"] == "E"
        assert buckets["55555555"] == "D"
