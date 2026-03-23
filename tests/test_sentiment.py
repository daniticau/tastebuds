from tastebud.db.queries import compute_sentiment_summary


class TestComputeSentimentSummary:
    def test_no_reviews(self):
        assert compute_sentiment_summary(0.0, 0) == "No reviews yet"

    def test_highly_recommended(self):
        assert compute_sentiment_summary(0.9, 5) == "Highly recommended"

    def test_highly_recommended_exact_threshold(self):
        assert compute_sentiment_summary(0.8, 3) == "Highly recommended"

    def test_high_pct_but_too_few_reviews(self):
        # 80%+ but only 2 reviews — not enough for "Highly recommended"
        assert compute_sentiment_summary(0.85, 2) == "Generally positive"

    def test_generally_positive(self):
        assert compute_sentiment_summary(0.7, 10) == "Generally positive"

    def test_generally_positive_exact_threshold(self):
        assert compute_sentiment_summary(0.6, 5) == "Generally positive"

    def test_mixed_reviews(self):
        assert compute_sentiment_summary(0.5, 8) == "Mixed reviews"

    def test_mixed_reviews_exact_threshold(self):
        assert compute_sentiment_summary(0.4, 4) == "Mixed reviews"

    def test_not_well_received(self):
        assert compute_sentiment_summary(0.2, 10) == "Not well received"

    def test_zero_pct_with_reviews(self):
        assert compute_sentiment_summary(0.0, 5) == "Not well received"

    def test_perfect_score_single_review(self):
        # 100% positive but only 1 review — "Generally positive", not "Highly recommended"
        assert compute_sentiment_summary(1.0, 1) == "Generally positive"
