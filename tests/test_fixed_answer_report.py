from collections import Counter

from evaluation.fixed_answer_report import choose


def counts(wrong,excessive,empty=0,calls=0):
    return Counter(wrong=wrong,excessive_abstention=excessive,empty_responses=empty,logical_generation_calls=calls)


def test_no_expansion_when_wrong_approvals_increase_despite_fewer_abstentions():
    table=dict(A=counts(82,14),B=counts(94,16),C=counts(95,8),D=counts(95,6))
    assert choose(table)==dict(eligible=False,candidates=[],selected=None)


def test_candidate_must_strictly_reduce_total_failures():
    table=dict(A=counts(4,2),B=counts(4,2),C=counts(3,3),D=counts(5,0))
    assert not choose(table)['eligible']


def test_selection_tie_breaks_and_processing_failure_blocks():
    table=dict(A=counts(5,3),B=counts(4,2,2,10),C=counts(4,2,1,20),D=counts(4,2,1,15))
    assert choose(table)['selected']=='D'
    table['D']['processing_error']=1
    assert choose(table)['selected']=='C'
    table['C']['pending']=1
    assert choose(table)['selected']=='B'
