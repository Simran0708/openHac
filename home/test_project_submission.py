import datetime
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from reversion.models import Version

from home.models import *
from home import factories
from home import scenarios
from home.email import organizers

# don't try to use the static files manifest during tests
@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class ProjectSubmissionTestCase(TestCase):

    # The following tests apply to the community read-only page text
    # e.g. home/templates/home/community_read_only.html

    def get_visitors_from_past_round(self, scenario):
        return (
            ("not logged in", None),
            ("no comrade", factories.UserFactory()),
            ("only comrade", factories.ComradeFactory().account),
            ("organizer", factories.ComradeFactory(account__is_staff=True).account),
            ("applicant", scenario.applicant1.applicant.account),
            ("mentor", scenario.mentor.account),
            ("coordinator", scenario.coordinator.account),
            ("reviewer", scenario.reviewer.account),
        )

    def test_community_read_only_submission_text_cfp_closed(self):
        """
        This tests how the page for coordinators and mentors of a community
        looks between rounds (after interns have been selected
        but before the next round has been announced).

        Test home/templates/home/community_read_only.html:
         - Create a community that has been approved to participate in a past round
         - No new RoundPage for the upcoming round
         - Check:
           - Warning card about CFP not being open is visible
           - The 'Submit a Project Proposal' button is not visible
           - The 'Submit an Outreachy Intern Project Proposal' heading is not visible
         - Ensure those checks are true for all visitor types
        """
        scenario = scenarios.InternshipWeekScenario(week = 1, community__name='Debian', community__slug='debian')
        community_read_only_path = reverse('community-read-only', kwargs={ 'community_slug': scenario.participation.community.slug, })
        project_submission_path = reverse('project-action', kwargs={'action': 'submit', 'round_slug': scenario.participation.participating_round.slug, 'community_slug': scenario.participation.community.slug, })

        visitors = self.get_visitors_from_past_round(scenario)

        for visitor_type, visitor in visitors:
            with self.subTest(visitor_type=visitor_type):
                self.client.logout()
                if visitor:
                    self.client.force_login(visitor)
                response = self.client.get(community_read_only_path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<div class="card-header text-white bg-warning">Project and community CFP is currently closed</div>', html=True)
                self.assertNotContains(response, '<h2>Submit an Outreachy Intern Project Proposal</h2>', html=True)
                self.assertNotContains(response, '<a class="btn btn-success" href="{}">Submit a Project Proposal</a>'.format(project_submission_path), html=True)

    def test_community_read_only_submission_text_cfp_open_uncertain_participation(self):
        """
        This tests how the page for coordinators and mentors of a community
        looks after a new round has been announced,
        but before the community signs up to participate.

        Test home/templates/home/community_read_only.html:
         - Create a community that has been approved to participate in a past round
         - Create a new RoundPage for the upcoming round
         - Check:
           - The 'Not Participating' status is visible
           - The 'Coordinate for This Community' button is visible to anyone who is not a coordinator
           - The 'Community will participate' button is visible to a coordinator
           - The 'Community will not participate' button is visible to a coordinator
           - The 'Submit a Project Proposal' button is not visible
           - The 'Submit an Outreachy Intern Project Proposal' heading is not visible
        """
        scenario = scenarios.InternshipWeekScenario(week = 10, community__name='Debian', community__slug='debian')
        community_read_only_path = reverse('community-read-only', kwargs={ 'community_slug': scenario.participation.community.slug, })
        current_round = factories.RoundPageFactory(start_from='pingnew')

        project_submission_path = reverse('project-action', kwargs={'action': 'submit', 'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, })
        coordinator_signup_path = reverse('coordinatorapproval-action', kwargs={'action': 'submit', 'community_slug': scenario.participation.community.slug, })
        community_does_participate_path = reverse('participation-action', kwargs={'action': 'submit', 'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, })
        community_does_not_participate_path = reverse('participation-action', kwargs={'action': 'withdraw', 'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, })

        visitors = self.get_visitors_from_past_round(scenario)

        for visitor_type, visitor in visitors:
            with self.subTest(visitor_type=visitor_type):
                self.client.logout()
                if visitor:
                    self.client.force_login(visitor)
                response = self.client.get(community_read_only_path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<span class="badge badge-pill badge-warning">Not Participating</span>', html=True)
                if visitor_type != 'coordinator':
                    self.assertContains(response, '<a href="{}" class="btn btn-success">Coordinate for This Community</a>'.format(coordinator_signup_path), html=True)
                else:
                    self.assertContains(response, '<a href="{}" class="btn btn-success">Community will participate</a>'.format(community_does_participate_path), html=True)
                    self.assertContains(response, '<a href="{}" class="btn btn-warning">Community will not participate</a>'.format(community_does_not_participate_path), html=True)
                self.assertNotContains(response, '<h2>Submit an Outreachy Intern Project Proposal</h2>', html=True)
                self.assertNotContains(response, '<a class="btn btn-success" href="{}">Submit a Project Proposal</a>'.format(project_submission_path), html=True)

    def coordinator_signs_up_community_to_participate(self, account, community_does_participate_path, sponsor_name='Software in the Public Interest - Debian', sponsor_amount=13000):
        self.client.force_login(account)
        return self.client.post(community_does_participate_path, {
            'sponsorship_set-TOTAL_FORMS': '1',
            'sponsorship_set-INITIAL_FORMS': '0',
            'sponsorship_set-MIN_NUM_FORMS': '0',
            'sponsorship_set-MAX_NUM_FORMS': '1000',
            'sponsorship_set-0-name': sponsor_name,
            'sponsorship_set-0-amount': sponsor_amount,
            'sponsorship_set-0-funding_secured': 'on',
            'sponsorship_set-0-funding_decision_date': str(datetime.date.today()),
        })

    def submit_failed_community_signup(self, current_round):
        scenario = scenarios.InternshipWeekScenario(week = 10, community__name='Debian', community__slug='debian')

        response = self.coordinator_signs_up_community_to_participate(
                scenario.coordinator.account,
                reverse('participation-action', kwargs={'action': 'submit', 'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, }),
                )
        with self.assertRaises(Participation.DoesNotExist):
            p = Participation.objects.get(community__slug=scenario.participation.community.slug, participating_round__slug=current_round.slug)
        self.assertNotEqual(response.status_code, 302)

    def test_community_participation_signup_too_early(self):
        """
        This tests submitting an older community to participate in this round.
         - Create a community that has been approved to participate in a past round
           (the past round is currently in week 10 of the internship)
         - Create a new RoundPage for the upcoming round where the CFP hasn't opened
         - Try to submit the community to participate in the round through the form
         - It should fail
        """
        current_round = factories.RoundPageFactory(start_from='pingnew', start_date=datetime.date.today() + datetime.timedelta(days=1))
        self.submit_failed_community_signup(current_round)

    def test_community_participation_signup_too_late(self):
        """
        This tests submitting an older community to participate in this round.
         - Create a community that has been approved to participate in a past round
           (the past round is currently in week 10 of the internship)
         - Create a new RoundPage for the upcoming round where the CFP is closed to new communities
         - Try to submit the community to participate in the round through the form
         - It should fail
        """
        current_round = factories.RoundPageFactory(start_from='lateorgs')
        self.submit_failed_community_signup(current_round)

    def test_old_community_participation_signup(self):
        """
        This tests submitting an older community to participate in this round.
         - Create a community that has been approved to participate in a past round
         - Create a new RoundPage for the upcoming round
         - Submit the community to participate in the round through the form
         - There should be an email sent to the Outreachy organizers about the participation
         - There should be a Participation object for this community in the current round marked as PENDING

        Test home/templates/home/community_read_only.html:
         - Check:
           - The 'Pending Participation' status is visible
           - Funding for 2 interns is visible
           - The 'Coordinate for This Community' button is visible to anyone who is not a coordinator
           - The 'Submit a Project Proposal' button is visible
           - The 'Submit an Outreachy Intern Project Proposal' heading is visible
           - The 'Community will participate' button is visible to a coordinator
           - The 'Community will not participate' button is visible to a coordinator
        """
        scenario = scenarios.InternshipWeekScenario(week = 10, community__name='Debian', community__slug='debian')
        current_round = factories.RoundPageFactory(start_from='pingnew')

        community_read_only_path = reverse('community-read-only', kwargs={ 'community_slug': scenario.participation.community.slug, })
        project_submission_path = reverse('project-action', kwargs={'action': 'submit', 'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, })
        coordinator_signup_path = reverse('coordinatorapproval-action', kwargs={'action': 'submit', 'community_slug': scenario.participation.community.slug, })
        community_does_participate_path = reverse('participation-action', kwargs={'action': 'submit', 'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, })
        community_does_not_participate_path = reverse('participation-action', kwargs={'action': 'withdraw', 'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, })
        sponsor_name = 'Software in the Public Interest - Debian'
        sponsor_amount = 13000

        visitors = self.get_visitors_from_past_round(scenario)
        # There should not be a Participation for Debian in the current round yet
        with self.assertRaises(Participation.DoesNotExist):
            p = Participation.objects.get(community__slug=scenario.participation.community.slug, participating_round__slug=current_round.slug)

        response = self.coordinator_signs_up_community_to_participate(
                scenario.coordinator.account,
                reverse('participation-action', kwargs={'action': 'submit', 'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, }),
                sponsor_name,
                sponsor_amount,
                )
        self.assertEqual(response.status_code, 302)

        # Ensure the database reflects the community sign-up
        participation = Participation.objects.get(community__slug=scenario.participation.community.slug, participating_round__slug=current_round.slug, approval_status=ApprovalStatus.PENDING)
        sponsorship = Sponsorship.objects.get(participation=participation, coordinator_can_update=True, name=sponsor_name, amount=sponsor_amount, funding_secured=True)

        # Make sure the email to the Outreachy organizers was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Approve community participation - Debian')
        self.assertEqual(mail.outbox[0].from_email, organizers)
        self.assertEqual(mail.outbox[0].to, [organizers])
        self.assertIn(community_read_only_path, mail.outbox[0].body)
        self.assertIn('Number of interns funded: 2', mail.outbox[0].body)
        self.assertIn(sponsor_name, mail.outbox[0].body)
        self.assertIn(str(sponsor_amount), mail.outbox[0].body)

        for visitor_type, visitor in visitors:
            with self.subTest(visitor_type=visitor_type):
                self.client.logout()
                if visitor:
                    self.client.force_login(visitor)
                response = self.client.get(community_read_only_path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<span class="badge badge-pill badge-info">Pending Participation</span>', html=True)
                self.assertContains(response, '<span class="badge badge-pill badge-success">Funded</span>', html=True)
                self.assertContains(response, '<td>This community has funding for 2 interns.</td>', html=True)
                self.assertContains(response, '<span class="badge badge-pill badge-warning">No Projects</span>', html=True)
                self.assertContains(response, '<span class="badge badge-pill badge-info">Open to New Projects</span>', html=True)
                if visitor_type != 'coordinator':
                    self.assertContains(response, '<a href="{}" class="btn btn-success">Coordinate for This Community</a>'.format(coordinator_signup_path), html=True)
                self.assertContains(response, '<h2>Submit an Outreachy Intern Project Proposal</h2>', html=True)
                self.assertContains(response, '<a class="btn btn-success" href="{}">Submit a Project Proposal</a>'.format(project_submission_path), html=True)

    def test_community_participation_approval(self):
        """
        This tests approving a community to participate in this round.
         - Create a new RoundPage for the upcoming round, with a pending community
         - Go to the community read-only page
         - Log in as an organizer
         - The community read-only page should have an 'Approve Community' and a 'Reject Community' button
         - Post to the Participation approval URL
         - This should redirect back to community read-only page
         - Participation should now marked as approved in the database
         - Coordinator receives email that the community was approved to participate
         - The community read-only page should now reflect that the community has been approved
           - Community status box should read 'Participating'
         - There should still be a way to submit projects

        Test home/templates/home/community_read_only.html:
         - Check:
           - The 'Participating' status is visible
           - Funding for 1 intern is visible
           - The 'Coordinate for This Community' button is visible to anyone who is not a coordinator
           - The 'Submit a Project Proposal' button is visible
           - The 'Submit an Outreachy Intern Project Proposal' heading is visible
           - The 'Community will participate' button is visible to a coordinator
           - The 'Community will not participate' button is visible to a coordinator
        """
        scenario = scenarios.InternshipWeekScenario(week = 10, community__name='Debian', community__slug='debian')
        current_round = factories.RoundPageFactory(start_from='pingnew')

        community_read_only_path = reverse('community-read-only', kwargs={ 'community_slug': scenario.participation.community.slug, })
        project_submission_path = reverse('project-action', kwargs={'action': 'submit', 'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, })
        coordinator_signup_path = reverse('coordinatorapproval-action', kwargs={'action': 'submit', 'community_slug': scenario.participation.community.slug, })
        community_does_participate_path = reverse('participation-action', kwargs={'action': 'submit', 'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, })
        approve_participation_path = reverse('participation-action', kwargs={'action': 'approve', 'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, })
        reject_participation_path = reverse('participation-action', kwargs={'action': 'reject', 'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, })
        visitors = self.get_visitors_from_past_round(scenario)

        # Set up the community with a pending participation in the current round
        participation = factories.ParticipationFactory(community=scenario.community, participating_round=current_round, approval_status=ApprovalStatus.PENDING)
        sponsorship = factories.SponsorshipFactory(participation=participation, name='Software in the Public Interest - Debian', amount=13000)
        
        organizer_account = User.objects.get(is_staff=True)
        self.client.force_login(organizer_account)

        # Double check that the community read-only page has links to approve or reject
        response = self.client.get(community_read_only_path)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<span class="badge badge-pill badge-info">Pending Participation</span>', html=True)
        self.assertContains(response, '<input type="submit" class="btn btn-success m-2" value="Approve Community" />', html=True)
        self.assertContains(response, '<a href="{}" class="btn btn-warning m-2">Reject Community</a>'.format(reject_participation_path), html=True)

        # Approve the community
        response = self.client.post(approve_participation_path)
        self.assertEqual(response.status_code, 302)

        # Check the database status
        approved_participation = Participation.objects.get(community__slug=participation.community.slug, participating_round__slug=current_round.slug, approval_status=ApprovalStatus.APPROVED)

        # Check that the email to the community coordinator was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, '{} is participating in Outreachy!'.format(scenario.community.name))
        self.assertEqual(mail.outbox[0].from_email, organizers)
        self.assertEqual(mail.outbox[0].to, scenario.community.get_coordinator_email_list())
        self.assertIn('The Outreachy organizers have approved {} to participate in the current round of Outreachy!'.format(scenario.community.name), mail.outbox[0].body)
        # TODO: we should probably check that other information is correct,
        # like the round dates, but this is enough for now.

        # Check that the community read-only page reflects the database status
        for visitor_type, visitor in visitors:
            with self.subTest(visitor_type=visitor_type):
                self.client.logout()
                if visitor:
                    self.client.force_login(visitor)
                response = self.client.get(community_read_only_path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<span class="badge badge-pill badge-success">Participating</span>', html=True)
                self.assertContains(response, '<span class="badge badge-pill badge-success">Funded</span>', html=True)
                self.assertContains(response, '<td>This community has funding for 2 interns.</td>', html=True)
                self.assertContains(response, '<span class="badge badge-pill badge-warning">No Projects</span>', html=True)
                self.assertContains(response, '<span class="badge badge-pill badge-info">Open to New Projects</span>', html=True)
                if visitor_type != 'coordinator':
                    self.assertContains(response, '<a href="{}" class="btn btn-success">Coordinate for This Community</a>'.format(coordinator_signup_path), html=True)
                self.assertContains(response, '<h2>Submit an Outreachy Intern Project Proposal</h2>', html=True)
                self.assertContains(response, '<a class="btn btn-success" href="{}">Submit a Project Proposal</a>'.format(project_submission_path), html=True)

    def mentor_submits_project_description(self, current_round, scenario):
        short_title = 'Improve Debian bioinformatics packages test coverage'
        long_description = 'The Debian Med project has packaged a lot of <a href="http://blends.debian.org/med/tasks/bio">applications for bioinformatics</a>. You will be improving the test coverage of those packages.'
        minimum_system_requirements = 'A system running Debian Linux'
        contribution_tasks = 'Look at issues marked newcomers-welcome.'
        repository = 'https://salsa.debian.org/med-team'
        issue_tracker = 'https://bugs.debian.org/'
        newcomer_issue_tag = 'newcomers-welcome'
        intern_tasks = 'Interns will work on new tests for <a href="http://blends.debian.org/med/tasks/bio">Debian bioinformatics packages</a>.'
        intern_benefits = 'Interns will develop skills in quality assurance testing, learn Linux command-line tools, and gain knowledge in how Linux distributions like Debian package software.'
        community_benefits = 'Debian maintainers will spend less time tracking down bugs in newly released software.'

        project_submission_path = reverse('project-action', kwargs={'action': 'submit', 'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, })

        # Submit project description
        self.client.force_login(scenario.mentor.account)
        response = self.client.post(project_submission_path, {
            'approved_license': 'on',
            'no_proprietary_software': 'on',
            'longevity': '2Y',
            'community_size': '20',
            'short_title': short_title,
            'long_description': long_description,
            'minimum_system_requirements': minimum_system_requirements,
            'contribution_tasks': contribution_tasks,
            'repository': repository,
            'issue_tracker': issue_tracker,
            'newcomer_issue_tag': newcomer_issue_tag,
            'intern_tasks': intern_tasks,
            'intern_benefits': intern_benefits,
            'community_benefits': community_benefits,
            'new_contributors_welcome': True,
            },
            # This says we're supposed to follow any and all redirects to other pages after the post
            # This will allow us to record a history of where the redirect went to
            follow=True,
        )

        # Ensure the Project object has been saved
        project = Project.objects.get(
                short_title=short_title,
                long_description=long_description,
                minimum_system_requirements=minimum_system_requirements,
                contribution_tasks=contribution_tasks,
                repository=repository,
                issue_tracker=issue_tracker,
                newcomer_issue_tag=newcomer_issue_tag,
                intern_tasks=intern_tasks,
                intern_benefits=intern_benefits,
                community_benefits=community_benefits,
                new_contributors_welcome=True,
        )
        return response, project

    def mentor_submits_project_mentor_profile(self, scenario, project, mentorapproval_submission_path):
        # Mentor profile information
        instructions_read='on',
        understands_intern_time_commitment='on',
        understands_applicant_time_commitment='on',
        understands_mentor_contract='on',
        mentored_before='OUT'
        mentorship_style='Weekly meetings by phone or video chat.'
        longevity='2Y'
        mentor_foss_contributions="I'm a Debian maintainer on the Debian Med team."
        communication_channel_username='foobar'

        response = self.client.post(mentorapproval_submission_path, {
            'instructions_read': instructions_read,
            'understands_intern_time_commitment': understands_intern_time_commitment,
            'understands_applicant_time_commitment': understands_applicant_time_commitment,
            'understands_mentor_contract': understands_mentor_contract,
            'mentored_before': mentored_before,
            'mentorship_style': mentorship_style,
            'longevity': longevity,
            'mentor_foss_contributions': mentor_foss_contributions,
            'communication_channel_username': communication_channel_username,
            },
            follow=True,
        )

        # Check that the MentorApproval was saved
        mentorapproval = MentorApproval.objects.get(
                mentor=scenario.mentor,
                project=project,
                mentored_before=mentored_before,
                mentorship_style=mentorship_style,
                longevity=longevity,
                mentor_foss_contributions=mentor_foss_contributions,
                communication_channel_username=communication_channel_username,
                instructions_read=True,
                understands_intern_time_commitment=True,
                understands_applicant_time_commitment=True,
                understands_mentor_contract=True,
        )
        return response

    def mentor_submits_project_skill(self, project, projectskill_submission_path):
        skill = 'Command-line skills'
        experience_level = 'EXP'
        required = 'OPT'

        response = self.client.post(projectskill_submission_path, {
            'projectskill_set-TOTAL_FORMS': '1',
            'projectskill_set-INITIAL_FORMS': '0',
            'projectskill_set-MIN_NUM_FORMS': '0',
            'projectskill_set-MAX_NUM_FORMS': '1000',
            'projectskill_set-0-skill': skill,
            'projectskill_set-0-experience_level': experience_level,
            'projectskill_set-0-required': required,
            },
            follow=True,
        )
        projectskill = ProjectSkill.objects.get(
                project=project,
                skill=skill,
                experience_level=experience_level,
                required=required,
        )
        return response

    def mentor_submits_project_communication_channel(self, project, projectcommunicationchannel_submission_path):
        tool_name='IRC'
        url='irc://irc.debian.org/#debian-med'
        instructions='Let the channel know you are an Outreachy applicant.'
        norms="Please read Debian's <a href='https://wiki.debian.org/GettingHelpOnIrc'>instructions for asking for help on IRC</a>."
        communication_help='https://wiki.debian.org/GettingHelpOnIrc'

        response = self.client.post(projectcommunicationchannel_submission_path, {
            'communicationchannel_set-TOTAL_FORMS': '1',
            'communicationchannel_set-INITIAL_FORMS': '0',
            'communicationchannel_set-MIN_NUM_FORMS': '0',
            'communicationchannel_set-MAX_NUM_FORMS': '1000',
            'communicationchannel_set-0-tool_name': tool_name,
            'communicationchannel_set-0-url': url,
            'communicationchannel_set-0-instructions': instructions,
            'communicationchannel_set-0-norms': norms,
            'communicationchannel_set-0-communication_help': communication_help,
            },
            follow=True,
        )

        communicationchannel = CommunicationChannel.objects.get(
                project=project,
                tool_name=tool_name,
                url=url,
                instructions=instructions,
                norms=norms,
                communication_help=communication_help,
        )
        return response

    def check_project_submission(self, scenario, current_round, participation):
        sponsorship = factories.SponsorshipFactory(participation=participation, name='Software in the Public Interest - Debian', amount=13000)

        visitors = self.get_visitors_from_past_round(scenario)

        response, project = self.mentor_submits_project_description(current_round, scenario)

        # Make sure the redirect went to the right place
        mentorapproval_submission_path = reverse('mentorapproval-action', kwargs={'action': 'submit', 'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, 'project_slug': project.slug, })
        self.assertRedirects(response, mentorapproval_submission_path)

        response = self.mentor_submits_project_mentor_profile(scenario, project, mentorapproval_submission_path)

        # Check that they're redirected to the project skills form
        projectskill_submission_path = reverse('project-skills-edit', kwargs={'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, 'project_slug': project.slug, })
        self.assertRedirects(response, projectskill_submission_path)

        response = self.mentor_submits_project_skill(project, projectskill_submission_path)

        # Check that they're redirected to the project communication channels form
        projectcommunicationchannel_submission_path = reverse('communication-channels-edit', kwargs={'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, 'project_slug': project.slug, })
        self.assertRedirects(response, projectcommunicationchannel_submission_path)

        response = self.mentor_submits_project_communication_channel(project, projectcommunicationchannel_submission_path)

        # Check that they're redirected to the project read only page
        project_read_only_path = reverse('project-read-only', kwargs={'round_slug': current_round.slug, 'community_slug': scenario.participation.community.slug, 'project_slug': project.slug, })
        self.assertRedirects(response, project_read_only_path)

        # Check coordinator receives email about the pending project
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Approve Outreachy intern project proposal for {}'.format(scenario.community.name))
        self.assertEqual(mail.outbox[0].from_email, organizers)
        self.assertEqual(mail.outbox[0].to, scenario.community.get_coordinator_email_list())
        self.assertIn('Please carefully review the project to ensure it is appropriate for Outreachy:', mail.outbox[0].body)
        self.assertIn(project_read_only_path, mail.outbox[0].body)

        # The community read-only page should not reflect the project was submitted, except to the mentor who submitted it

    def test_project_submission_by_old_mentor_to_pending_community(self):
        """
        This tests submitting a project to a community that is pending approval to participate in this round.
         - Create a new RoundPage for the upcoming round, with a pending community
         - Go to the community read-only page
         - Log in as a mentor from the previous round for this community
         - Click the 'Submit Project' button, fill out project description
         - Be redirected to the MentorApproval form, fill that out
         - Be redirected to the ProjectSkills form, fill that out
         - Be redirected to the ProjectCommunicationChannels form, fill that out
         - Finally be done! \o/
         - Coordinator receives email about the pending project
         - The community read-only page should not reflect the project was submitted, except to the mentor who submitted it
        """
        scenario = scenarios.InternshipWeekScenario(week = 10, community__name='Debian', community__slug='debian')

        current_round = factories.RoundPageFactory(start_from='pingnew')
        participation = factories.ParticipationFactory(community=scenario.community, participating_round=current_round, approval_status=ApprovalStatus.PENDING)

        self.check_project_submission(scenario, current_round, participation)

    def test_project_submission_to_approved_community(self):
        """
        This tests submitting a project to a community that is approved to participate in this round.
         - Create a new RoundPage for the upcoming round, with an approved community
         - Go to the community read-only page
         - Log in as a mentor from the previous round for this community
         - Click the 'Submit Project' button, fill out project description
         - Be redirected to the MentorApproval form, fill that out
         - Be redirected to the ProjectSkills form, fill that out
         - Be redirected to the ProjectCommunicationChannels form, fill that out
         - Finally be done! \o/
         - Coordinator receives email about the pending project
         - The community read-only page should not reflect the project was submitted, except to the mentor who submitted it
        """
        scenario = scenarios.InternshipWeekScenario(week = 10, community__name='Debian', community__slug='debian')

        current_round = factories.RoundPageFactory(start_from='pingnew')
        participation = factories.ParticipationFactory(community=scenario.community, participating_round=current_round, approval_status=ApprovalStatus.APPROVED)

        self.check_project_submission(scenario, current_round, participation)

    def test_project_soft_deadline(self):
        """
        This tests submitting a project after the deadline for project approval fails:
         - Create a new RoundPage for the upcoming round with the project submission deadline passed
         - Create an approved community
         - Go to the community read-only page
         - There should not be a 'Submit Project' button
         - Submitting a project directly via the URL should still work
        """
        scenario = scenarios.InternshipWeekScenario(week = 14, community__name='Debian', community__slug='debian')

        # The "soft" deadline is actually six days before lateprojects
        # (denoted by RoundPage.project_soft_deadline())
        # On the soft deadline, the community CFP page shows project submission is closed.
        # The community read-only page doesn't show the submit button.
        # *But* mentors can still submit if they know the URL.
        # This allows us to deal with the few mentors who always miss the deadline.
        current_round = factories.RoundPageFactory(start_from='lateprojects', start_date=datetime.date.today() + datetime.timedelta(days=6))
        participation = factories.ParticipationFactory(community=scenario.community, participating_round=current_round, approval_status=ApprovalStatus.APPROVED)

        # TODO: check community read-only page to ensure submission button is missing

        self.check_project_submission(scenario, current_round, participation)

    def test_project_display_on_community_read_only(self):
        pass

    def test_community_cfp_closed(self):
        # This is before we have a new RoundPage for the upcoming round,
        # and after the interns are announced for the last round.
        # InternshipWeekScenario(week=5)
        #
        # /community/cfp should be linked from the mentor instructions (currently in the Wagtail CRM)
        # /community/cfp should be linked from the navigational menu
        # - Volunteers -> 'Add a community'
        # - Volunteers -> 'Submit a project'
        # - Volunteers -> 'Co-mentor a project'
        #
        # On /community/cfp:
        #  - The generic timeline should be visible.
        #  - There should not be a button to submit a new community to participate.
        #  - Communities who have participated in the past should be listed on the website.
        #  - There should be a list of communities who were not approved to participate in any round.
        #  - Historic communities (with no participation objects at all) should be listed separately.
        #
        # New community coordinators should be able to sign up for the upcoming round:
        #  - Click on a community from /community/cfp/
        #  - There should be a link to the coordinator duties "/mentor/#coordinator"
        #  x There should be a button "Coordinate for this Community"
        #  - CoordinatorApproval submission form should work
        #  - Outreachy organizers and current approved Coordinators should get an email notification
        #  - following the link sent from that email should allow both approval and rejection
        #  - the person should get an email on both approval or rejection
        #  - the rejection email should include the reason for rejection
        #  - approval should now show the coordinator listed on the community read-only page
        #
        # Sign up to be notified when the community is participating in the next round:
        #  - Click on a community from /community/cfp/
        #  - There should be a "Notify me" button
        #  - Notification form should work
        #  - When the round opens, everyone who signed up to be notified should get an email
        pass

    def test_community_cfp_open(self):
        # This is when we have a new RoundPage and the community sign-ups are open
        # today = datetime.date.today()
        # NewRoundScenario(round__start_from='pingnew', round__start_date=today)
        #
        # On /community/cfp:
        #  - The timeline for this round should now be visible.
        #  - The "Community sign up opens" should match today's date
        #  - Past participating communities should include the one created by NewRoundScenario
        #  - Create a "historic" community - it should be shown
        #  - Create an "unapproved" community from last round - should be shown
        #
        # Past coordinator signing up for the current round:
        #  - Go to /community/cfp/
        #  - Follow the link for your community
        #  - Get confused by why there's a 'sign-up to coordinate' button when you're a coordinator
        #  x Log into the website, which should redirect back to the community read-only page
        #  x There should be a success color 'Community Will Participate' button
        #  x Click that button, fill out funding form
        #  - The community read-only page should now reflect that the community has signed up
        #    - Coordinator actions box with 'Update community info' button
        #    x Community status box should read 'Pending Participation'
        #    x Funding should reflect funding levels coordinator put in
        #    x 'No projects' are approved by the coordinator yet
        #    x 'Open to new projects' - mentors can submit projects
        #    x 'Submit a Project Proposal' button for mentors to submit projects
        #    - A link to the mentor FAQ should be visible 'mentor requirements'
        #  x Outreachy organizers should get an email about the community sign up
        #
        # Mentor should be able to submit a project:
        #  - FIXME - need detailed description of this process
        #
        # Organizer approving the community:
        #  x Outreachy organizers should follow the link from the email, log in, and be able to approve the community
        #  x The link should have an 'Approve Community' button
        #  x Redirect back to community read-only page
        #  x Coordinator receives email that the community was approved to participate
        #  x The community read-only page should now reflect that the community has been approved
        #    x Community status box should read 'Participating'
        #
        # Organizer rejecting the community:
        #  - Outreachy organizers should follow the link from the email, log in, and be able to reject the community
        #  - The link should have an warning color 'Reject Community' button
        #  - Need to click a second reject button on the double confirmation page, and provide a reason for rejection
        #  - Redirect back to community read-only page
        #  - Coordinator will not receive automated email that they were rejected - organizers will send a personalized email
        #  - The community read-only page should now reflect that the community has not been approved
        #    - Community status box should read 'Not Participating'
        #  - The community should not show up under /apply/project-selection/
        #  - Any approved projects for that community should not show up on /apply/project-selection/
        #
        # Past coordinator saying the community will not participate:
        #  - Go to /community/cfp/
        #  - Follow the link for your community
        #  - Get confused by why there's a 'sign-up to coordinate' button when you're a coordinator
        #  - Log into the website, which should redirect back to the community read-only page
        #  - There should be a warning color 'Community Will Not Participate' button
        pass
