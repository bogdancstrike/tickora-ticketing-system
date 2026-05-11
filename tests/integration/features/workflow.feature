Feature: Ticket workflow

  Scenario: Sector member takes ownership of an assigned ticket
    Given a pending ticket routed to sector s10
    When a sector member assigns the ticket to themselves
    Then the ticket is in progress and assigned to that member
    And assignment status and audit entries are recorded

  Scenario: Assignee resolves a ticket
    Given an in-progress ticket assigned to a sector member
    When the assignee marks the ticket done with a resolution
    Then the ticket is done with a done history entry

  Scenario: Beneficiary reopens a done ticket
    Given a done ticket with a last active assignee
    When the beneficiary reopens the ticket
    Then the ticket is in progress for the last active assignee
