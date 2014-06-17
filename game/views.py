import json
import os
import messages

from cache import cached_all_levels, cached_max_level, cached_level
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template import RequestContext
from django.utils.safestring import mark_safe
from forms import AvatarPreUploadedForm, AvatarUploadForm, ShareLevel, ScoreboardForm
from game import random_road
from models import Class, Level, Attempt, Command, Block


def levels(request):
    context = RequestContext(request, {
        'levels': cached_all_levels()
    })
    return render(request, 'game/level_selection.html', context)


def level(request, level):
    """Loads a level for rendering in the game

    **Template:**

    :template:`game/game.html`
    """
    lvl = cached_level(level)
    blocks = lvl.blocks.order_by('id')
    attempt = None
    lesson = None
    levelCount = cached_max_level()
    if int(level) <= levelCount:
        lesson = 'description_level' + str(level)
        hint = 'hint_level' + str(level)
    else:
        lesson = 'description_level_default'
        hint = 'hint_level_default'
    messageCall = getattr(messages, lesson)
    lesson = mark_safe(messageCall())
    messageCall = getattr(messages, hint)
    hint = mark_safe(messageCall())

    #FIXME: figure out how to check for all this better
    if not request.user.is_anonymous() and hasattr(request.user, 'userprofile') and \
            hasattr(request.user.userprofile, 'student'):
        student = request.user.userprofile.student
        try:
            attempt = get_object_or_404(Attempt, level=lvl, student=student)
        except Http404:
            attempt = Attempt(level=lvl, score=0, student=student)
            attempt.save()

    context = RequestContext(request, {
        'level': lvl,
        'blocks': blocks,
        'lesson': lesson,
        'hint': hint,
        'defaultLevelCount': levelCount,
    })

    return render(request, 'game/game.html', context)


def level_new(request):
    """Processes a request on creation of the map in the level editor."""
    if 'nodes' in request.POST:
        path = request.POST['nodes']
        destination = request.POST['destination']
        decor = request.POST['decor']
        maxFuel = request.POST['maxFuel']
        name = request.POST.get('name')
        passedLevel = None
        passedLevel = Level(name=name, path=path, default=False, destination=destination, decor=decor, maxFuel=maxFuel)

        if not request.user.is_anonymous() and hasattr(request.user, 'userprofile') and hasattr(request.user.userprofile, 'student'):
            passedLevel.owner = request.user.userprofile
        passedLevel.save()

        if 'blockTypes' in request.POST:
            blockTypes = json.loads(request.POST['blockTypes'])
            blocks = Block.objects.filter(type__in=blockTypes)
        else:
            blocks = Block.objects.all()

        passedLevel.blocks = blocks
        passedLevel.save()

        response_dict = {}
        response_dict.update({'server_response': passedLevel.id})
        return HttpResponse(json.dumps(response_dict), content_type='application/javascript')


def level_random(request):
    """Generates a new random level

    Redirects to :view:`game.views.level` with the id of the newly created :model:`game.Level` object
    """
    level = random_road.create()
    return redirect("game.views.level", level=level.id)


def submit(request):
    """ Processes a request on submission of the program solving the current level."""
    if request.method == 'POST' and 'attemptData' in request.POST:
        attemptJson = request.POST['attemptData']
        attemptData = json.loads(attemptJson)
        parseAttempt(attemptData, request)
        return HttpResponse(attemptJson, content_type='application/javascript')


def parseAttempt(attemptData, request):
    level = get_object_or_404(Level, id=attemptData.get('level', 1))
    attempt = get_object_or_404(Attempt, level=level, student=request.user.userprofile.student)
    attempt.score = request.POST.get('score', 0)

    # Remove all the old commands from previous attempts.
    Command.objects.filter(attempt=attempt).delete()
    commands = attemptData.get('commandStack', None)
    parseInstructions(json.loads(commands), attempt, 1)
    attempt.save()


def logged_students(request):
    """ Renders the page with information about all the logged in students."""
    return render_student_info(request, True)


def scoreboard(request):
    """ Renders a page with students' scores.

     **Template:**
    :template:`game/scoreboard.html`
    """
    teacher = request.user.userprofile.teacher
    form = ScoreboardForm(request.POST or None, teacher=teacher)
    students = None

    if request.method == 'POST':
        if form.is_valid():
            levelID = form.data.get('levels', False)
            classID = form.data.get('classes', False)
            cl = get_object_or_404(Class, id=classID)
            level = get_object_or_404(Level, id=levelID)
            students =  cl.students.all()


    context = RequestContext(request, {
        'form': form,
        'students': students
    })
    return render(request, 'game/scoreboard.html', context)


def level_editor(request):
    context = RequestContext(request, {
        'blocks': Block.objects.all()
    })
    return render(request, 'game/level_editor.html', context)


def settings(request):
    """ Renders the settings page.  """
    x = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(x, 'static/game/image/Avatars/')
    img_list = os.listdir(path)
    avatar = None
    modal = False
    userProfile = request.user.userprofile
    avatarUploadForm = AvatarUploadForm(request.POST or None, request.FILES)
    avatarPreUploadedForm = AvatarPreUploadedForm(request.POST or None, my_choices=img_list)
    shareLevelForm = ShareLevel(request.POST or None)
    studentLevels = Level.objects.filter(owner=userProfile.id)
    levelMessage = messages.noLevelsToShow() if len(studentLevels) == 0 else messages.levelsMessage() 
    if request.method == 'POST':
        if "pre-uploaded" in request.POST:
            if avatarPreUploadedForm.is_valid:
                avatar = avatarPreUploadedForm.data.get('pre-uploaded', False)
        elif "share-level" in request.POST and shareLevelForm.is_valid():
            message, people = handleSharedLevel(request, shareLevelForm)
            if avatarUploadForm.is_valid() and "user-uploaded" in request.POST:
                avatar = request.FILES.get('avatar', False)
        userProfile.avatar = avatar
        userProfile.save()

    context = RequestContext(request, {
        'avatarPreUploadedForm': avatarPreUploadedForm,
        'avatarUploadForm': avatarUploadForm,
        'shareLevelForm': shareLevelForm,
        'levels': studentLevels,
        'user': request.user,
        'levelMessage': levelMessage,
        'modal': modal
    })
    return render(request, 'game/settings.html', context)


def handleSharedLevel(request, form):
    level = get_object_or_404(Level, id=form.level)
    people = User.objects.filter(first_name=form.name, last_name=form.surname)
    message = None
    peopleLen = len(people)
    if peopleLen == 0:
        message = shareUnsuccessful(form.name, form.surname)
    elif peopleLen == 1:
        level.sharedWith.add(people[0])
        message = shareSuccessful(form.name, form.surname)
    return message, people


def render_student_info(request, logged):
    """ Helper method for rendering the studend info for a logged-in teacher."""
    user = request.user
    message = messages.chooseClass()
    currentClass = ""
    thead = ["Avatar", "Name", "Surname", "Levels attempted", "Levels completed", "Best level",
             "Best score", "Worst level", "Worst score"]
    students = []
    studentData = []

    if request.method == 'POST':
        cl = get_object_or_404(Class, id=request.POST.getlist('classes')[0])
        students = cl.get_logged_in_students() if logged else cl.students.all()
        currentClass = cl.name
    try:
        classes = user.userprofile.teacher.class_teacher.all()
    except ObjectDoesNotExist:
        message = messages.noPermission()

    for student in students:
        best = None
        worst = None
        # Exclude your own levels.
        levels = Attempt.objects.filter(student=student,
                                        level__owner__isnull=True).order_by('-score')
        # TODO: Add scoring so that we actually get some variation in best and worst fields.
        levels_completed = levels.exclude(score=0)
        if len(levels_completed) > 0:
            best = levels_completed[0]
            worst = levels_completed[len(levels_completed) - 1]
        studentData.append([student, len(levels), len(levels_completed), best, worst])

    context = RequestContext(request, {
        'classes': classes,
        'message': message,
        'thead': thead,
        'studentData': studentData,
        'currentClass': currentClass,
    })
    return render(request, 'game/logged_students.html', context)


def parseInstructions(instructions, attempt, init):
    """ Helper method for inserting user-submitted instructions to the database."""

    if not instructions:
        return
    command = None
    index = init

    for instruction in instructions:
        next = index + 1

        if instruction['command'] == 'Forward':
            command = Command(step=index, attempt=attempt, command='Forward', next=index+1)
        elif instruction['command'] == 'Left':
            command = Command(step=index, attempt=attempt, command='Left', next=index+1)
        elif instruction['command'] == 'Right':
            command = Command(step=index, attempt=attempt, command='Right', next=index+1)
        elif instruction['command'] == 'TurnAround':
            command = Command(step=index, attempt=attempt, command='TurnAround', next=index+1)

        elif instruction['command'] == 'While':
            condition = instruction['condition']
            parseInstructions(instruction['block'], attempt, next)
            execBlock = range(index + 1, index + len(instruction['block']) + 1)
            command = Command(step=index, attempt=attempt, command='While', condition=condition,
                              next=index+len(execBlock)+1, executedBlock1=execBlock)
            index += len(execBlock)

        elif instruction['command'] == 'If':
            condition = instruction['condition']
            parseInstructions(instruction['ifBlock'], attempt, next)
            next += len(instruction['ifBlock'])
            ifBlock = range(index + 1, next)

            if 'elseBlock' in instruction:
                parseInstructions(instruction['elseBlock'], attempt, next)
                next += len(instruction['elseBlock'])
                elseBlock = range(index + len(ifBlock) + 1, next + 2)
                command = Command(step=index, attempt=attempt, condition=condition, command='If',
                                  executedBlock1=ifBlock, executedBlock2=elseBlock, )
                index += len(elseBlock)
            else:
                command = Command(step=index, attempt=attempt, command='If', condition=condition,
                                  executedBlock1=ifBlock, next=next)
            index += len(ifBlock)

        else:
            command = Command(step=index, attempt=attempt, command='Forward', next=index+1)
        command.save()
        index += 1
    last = Command.objects.get(step=init+len(instructions)- 1, attempt=attempt)
    last.next = None
    last.save()
